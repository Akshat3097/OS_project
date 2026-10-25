"""
Error analysis: compare a student's answer with the OS Engine's answer and name
the ROOT CAUSE of each mistake, not just "wrong".

Two ideas make this more useful than answer matching:

1. Root cause vs. propagated error. If a student draws the wrong Gantt chart, their
   completion times will be wrong too, but if their turnaround/waiting times are
   consistent with their own (wrong) completion times, their formulas are fine.
   Those cells are marked "consistent" and the formula skills are not penalised.

2. Misconception detection. Many wrong answers come from a specific misconception
   (e.g. "waiting time = turnaround time", "higher number = higher priority",
   "the preempted process goes back before the new arrival"). The analyser
   re-runs the engine under these wrong rules and checks whether the student's
   answer matches. If it does, we know exactly what they believe.
"""
from __future__ import annotations

from engine import bankers, scheduling, semaphore
from engine.scheduling import IDLE, PREEMPTIVE, Segment

# category: decision = scheduling decision error (wrong Gantt chart)
#           calculation = arithmetic / formula error (Gantt chart right, numbers wrong)
#           format = answer is incomplete or malformed
# skill: which learning-profile skill this error counts against ("ALGO" = the problem's algorithm)
ERROR_CATALOG: dict[str, dict] = {
    "algorithm_confusion": {"category": "decision", "skill": "ALGO", "label": "Applied a different algorithm",
                            "misconception": "Mixing up the selection rules of two scheduling algorithms."},
    "priority_direction": {"category": "decision", "skill": "ALGO", "label": "Reversed priority order",
                           "misconception": "Treating a larger priority number as a higher priority."},
    "rr_requeue_order": {"category": "decision", "skill": "RR", "label": "RR queue order at slice end",
                         "misconception": "Putting the preempted process back in the queue before a process that arrived at the same instant."},
    "quantum_error": {"category": "decision", "skill": "RR", "label": "Time quantum not applied correctly",
                      "misconception": "Running a process for more or less than one time quantum."},
    "queue_order_error": {"category": "decision", "skill": "RR", "label": "Ready queue order",
                          "misconception": "Not taking the process at the front of the FIFO ready queue."},
    "ran_before_arrival": {"category": "decision", "skill": "ALGO", "label": "Scheduled a process before it arrived",
                           "misconception": "Ignoring arrival times when choosing the next process."},
    "missed_preemption": {"category": "decision", "skill": "ALGO", "label": "Missed a preemption",
                          "misconception": "Forgetting to compare a newly arrived process with the running one."},
    "unnecessary_preemption": {"category": "decision", "skill": "ALGO", "label": "Preempted without a reason",
                               "misconception": "Preempting when the new process is not strictly better."},
    "preempted_nonpreemptive": {"category": "decision", "skill": "ALGO", "label": "Preempted in a non-preemptive algorithm",
                                "misconception": "Interrupting a running process in a non-preemptive algorithm."},
    "tie_breaking": {"category": "decision", "skill": "ALGO", "label": "Tie-breaking rule",
                     "misconception": "Breaking a tie without using arrival order (FCFS) as the tie-breaker."},
    "wrong_selection": {"category": "decision", "skill": "ALGO", "label": "Chose the wrong process",
                        "misconception": "Not applying the algorithm's selection rule to all ready processes."},
    "unnecessary_idle": {"category": "decision", "skill": "ALGO", "label": "Left the CPU idle",
                         "misconception": "Leaving the CPU idle while a process was ready."},
    "burst_mismatch": {"category": "decision", "skill": "ALGO", "label": "Run time does not match burst time",
                       "misconception": "A process runs for longer or shorter than its burst time in total."},
    "gantt_format": {"category": "format", "skill": None, "label": "Gantt chart has gaps, overlaps or unknown processes",
                     "misconception": None},
    "ct_misread": {"category": "calculation", "skill": "CT_READING", "label": "Completion time read wrongly",
                   "misconception": "Completion time is the time the process finishes its LAST run in the Gantt chart."},
    "ct_first_segment": {"category": "calculation", "skill": "CT_READING", "label": "Used the end of the first run as completion time",
                         "misconception": "In preemptive scheduling a process can run in several pieces; CT is the end of the last piece."},
    "tat_forgot_arrival": {"category": "calculation", "skill": "TAT_FORMULA", "label": "TAT = CT (arrival time not subtracted)",
                           "misconception": "Turnaround time is measured from ARRIVAL, not from time 0: TAT = CT − AT."},
    "tat_wt_swapped": {"category": "calculation", "skill": "TAT_FORMULA", "label": "Swapped TAT and WT",
                       "misconception": "Confusing turnaround time with waiting time."},
    "arithmetic_tat": {"category": "calculation", "skill": "TAT_FORMULA", "label": "Turnaround time arithmetic",
                       "misconception": None},
    "wt_forgot_burst": {"category": "calculation", "skill": "WT_FORMULA", "label": "WT = TAT (burst time not subtracted)",
                        "misconception": "Waiting time excludes the time spent running: WT = TAT − BT."},
    "wt_used_response": {"category": "calculation", "skill": "WT_FORMULA", "label": "Used response time as waiting time",
                         "misconception": "Waiting time counts ALL time spent in the ready queue, not just the wait before the first run."},
    "wt_forgot_arrival": {"category": "calculation", "skill": "WT_FORMULA", "label": "WT = CT − BT (arrival time not subtracted)",
                          "misconception": "Waiting starts when the process arrives: WT = CT − AT − BT."},
    "wt_used_start": {"category": "calculation", "skill": "WT_FORMULA", "label": "Used start time as waiting time",
                      "misconception": "Waiting time is start time minus ARRIVAL time (for non-preemptive), not the start time itself."},
    "arithmetic_wt": {"category": "calculation", "skill": "WT_FORMULA", "label": "Waiting time arithmetic",
                      "misconception": None},
    "missing_value": {"category": "format", "skill": None, "label": "Missing value", "misconception": None},
    # banker's
    "need_sign_error": {"category": "calculation", "skill": "BANKERS_NEED", "label": "Need = Allocation − Max",
                        "misconception": "Need is what a process may still request: Need = Max − Allocation."},
    "need_used_max": {"category": "calculation", "skill": "BANKERS_NEED", "label": "Used Max as Need",
                      "misconception": "Forgetting to subtract what the process already holds."},
    "need_added": {"category": "calculation", "skill": "BANKERS_NEED", "label": "Need = Max + Allocation",
                   "misconception": "Need is Max minus Allocation, not the sum."},
    "need_arithmetic": {"category": "calculation", "skill": "BANKERS_NEED", "label": "Need matrix arithmetic", "misconception": None},
    "wrong_safety_verdict": {"category": "decision", "skill": "BANKERS_SAFETY", "label": "Wrong safe/unsafe verdict",
                             "misconception": "A state is safe only if EVERY process can finish in some order."},
    "invalid_sequence": {"category": "decision", "skill": "BANKERS_SAFETY", "label": "Sequence is not safe",
                         "misconception": "A process can be chosen only when its Need ≤ current Work."},
    "added_need_not_allocation": {"category": "decision", "skill": "BANKERS_SAFETY", "label": "Released Need instead of Allocation",
                                  "misconception": "When a process finishes it releases what it HOLDS (Allocation), so Work += Allocation."},
    "compared_max_not_need": {"category": "decision", "skill": "BANKERS_SAFETY", "label": "Compared Max (not Need) with Work",
                              "misconception": "The check is Need ≤ Work, because the process already holds its Allocation."},
    # semaphores
    "semaphore_clamped_zero": {"category": "calculation", "skill": "SEMAPHORE", "label": "Semaphore value never goes below 0",
                               "misconception": "In the blocking implementation the value goes negative; −k means k processes are waiting."},
    "semaphore_count_error": {"category": "calculation", "skill": "SEMAPHORE", "label": "Semaphore value miscounted", "misconception": None},
    "forgot_wakeup": {"category": "decision", "skill": "SEMAPHORE", "label": "Forgot that signal() wakes a waiting process",
                      "misconception": "signal() on a semaphore with waiting processes wakes one of them (FIFO)."},
    "missed_block": {"category": "decision", "skill": "SEMAPHORE", "label": "Missed a process that blocks",
                     "misconception": "wait() blocks the caller when the value becomes negative."},
}


def error_info(etype: str, algorithm: str | None = None) -> dict:
    info = dict(ERROR_CATALOG.get(etype, {"category": "calculation", "skill": None, "label": etype, "misconception": None}))
    if info.get("skill") == "ALGO":
        info["skill"] = algorithm
    return info


def _err(etype: str, algorithm: str | None, **detail) -> dict:
    info = error_info(etype, algorithm)
    return {"type": etype, **info, "detail": detail}


# ============================================================================ scheduling

def normalise_pid(x) -> str:
    s = str(x if x is not None else "").strip().upper()
    if s in ("", "-", "IDLE", "NONE", "NAN", "X"):
        return IDLE
    if s.isdigit():
        return f"P{s}"
    return s


def _to_int(x):
    if x is None:
        return None
    try:
        if isinstance(x, str) and not x.strip():
            return None
        f = float(x)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return int(round(f)) if abs(f - round(f)) < 1e-9 else f


def parse_gantt(rows: list) -> tuple[list[Segment], list[str]]:
    """rows: list of dicts {Process, Start, End} or tuples (pid, start, end)."""
    issues: list[str] = []
    raw: list[Segment] = []
    for r in rows or []:
        if isinstance(r, dict):
            pid, st, en = r.get("Process"), r.get("Start"), r.get("End")
        else:
            pid, st, en = r
        st_i, en_i = _to_int(st), _to_int(en)
        if (pid is None or str(pid).strip() == "" or str(pid) == "nan") and st_i is None and en_i is None:
            continue
        if st_i is None or en_i is None:
            issues.append(f"Row for {pid} is missing a start or end time.")
            continue
        if en_i <= st_i:
            issues.append(f"Row {pid} {st_i}-{en_i}: end must be after start.")
            continue
        raw.append(Segment(normalise_pid(pid), int(st_i), int(en_i)))
    raw.sort(key=lambda s: s.start)
    segs: list[Segment] = []
    t = 0
    for s in raw:
        if s.start < t:
            issues.append(f"{s.pid} starts at {s.start} but the CPU is already busy until {t} (overlap).")
            continue
        if s.start > t:
            segs.append(Segment(IDLE, t, s.start))
        segs.append(s)
        t = s.end
    return scheduling.merge_segments(segs), issues


def _alternative_explanations(problem, student_tl: list[str]) -> dict | None:
    """Does the student's whole chart match the schedule produced by a *wrong* rule?"""
    procs, algo = problem.processes, problem.algorithm
    candidates: list[tuple[str, dict, scheduling.ScheduleResult]] = []
    if algo in scheduling.USES_PRIORITY:
        candidates.append(("priority_direction", {}, scheduling.run(algo, procs, lower_is_higher=False)))
    if algo == "RR":
        candidates.append(("rr_requeue_order", {}, scheduling.round_robin(procs, problem.quantum, new_arrivals_first=False)))
        for q in range(1, 9):
            if q != problem.quantum:
                candidates.append(("quantum_error", {"used_quantum": q, "correct_quantum": problem.quantum},
                                   scheduling.round_robin(procs, q)))
    for other in scheduling.ALGORITHMS:
        if other == algo or other == "RR":
            continue
        if other in scheduling.USES_PRIORITY and algo not in scheduling.USES_PRIORITY:
            continue
        candidates.append(("algorithm_confusion", {"applied": other, "expected": algo}, scheduling.run(other, procs)))
    correct_tl = problem.solve().timeline()
    for etype, detail, res in candidates:
        tl = res.timeline()
        if tl == student_tl and tl != correct_tl:
            return {"type": etype, "detail": detail}
    return None


def _key(algo: str, entry: dict):
    return {"FCFS": entry["arrival"], "SJF": entry["burst"], "SRTF": entry["remaining"],
            "PRIORITY_NP": entry["priority"], "PRIORITY_P": entry["priority"]}.get(algo)


def _local_divergence(problem, correct, s_tl: list[str], c_tl: list[str]) -> tuple[dict, dict]:
    algo = problem.algorithm
    by_id = {p.pid: p for p in problem.processes}
    n = min(len(s_tl), len(c_tl))
    t0 = next((i for i in range(n) if s_tl[i] != c_tl[i]), n)
    s_pid = s_tl[t0] if t0 < len(s_tl) else None
    c_pid = c_tl[t0] if t0 < len(c_tl) else None
    prev = c_tl[t0 - 1] if t0 > 0 else None
    ready = scheduling.ready_state_at(correct, t0)
    ready_ids = {r["pid"] for r in ready}
    dec = scheduling.governing_decision(correct, t0)
    facts = {"time": t0, "student_pid": s_pid, "correct_pid": c_pid, "running_before": prev,
             "ready": ready, "correct_reason": dec.reason if dec and dec.time == t0 else None}
    if algo == "RR" and dec is not None and dec.time == t0:
        facts["queue"] = [r["pid"] for r in dec.ready]

    def e(etype, **d):
        return _err(etype, algo, time=t0, student_pid=s_pid, correct_pid=c_pid, **d)

    if s_pid is None or c_pid is None:
        return e("burst_mismatch", note="Gantt chart ends at the wrong time."), facts
    if s_pid != IDLE and s_pid not in by_id:
        return e("gantt_format", note=f"Unknown process {s_pid}."), facts
    if s_pid != IDLE and by_id[s_pid].arrival > t0:
        return e("ran_before_arrival", arrival=by_id[s_pid].arrival), facts
    if s_pid == IDLE:
        return e("unnecessary_idle"), facts
    if s_pid not in ready_ids:
        return e("burst_mismatch", note=f"{s_pid} has already finished its burst by t={t0}."), facts

    s_entry = next(r for r in ready if r["pid"] == s_pid)
    c_entry = next((r for r in ready if r["pid"] == c_pid), None)
    prev_running = prev not in (None, IDLE) and prev in ready_ids

    if algo == "RR":
        if prev_running and s_pid == prev and c_pid != prev:
            return e("quantum_error", note=f"{prev} kept the CPU beyond one quantum ({problem.quantum})."), facts
        if prev_running and c_pid == prev and s_pid != prev:
            return e("quantum_error", note=f"{prev} was switched out before its quantum ended."), facts
        alt = scheduling.round_robin(problem.processes, problem.quantum, new_arrivals_first=False).timeline()
        if t0 < len(alt) and alt[t0] == s_pid and alt[:t0] == c_tl[:t0]:
            return e("rr_requeue_order"), facts
        return e("queue_order_error", queue=facts.get("queue")), facts

    if algo in PREEMPTIVE:
        if prev_running and s_pid == prev and c_pid != prev:
            return e("missed_preemption", preempting=c_pid), facts
        if prev_running and c_pid == prev and s_pid != prev:
            if c_entry and _key(algo, s_entry) == _key(algo, c_entry):
                return e("tie_breaking"), facts
            return e("unnecessary_preemption"), facts
    else:
        if prev_running and c_pid == prev and s_pid != prev:
            return e("preempted_nonpreemptive", interrupted=prev), facts
        if prev_running and s_pid == prev and c_pid != prev:
            return e("burst_mismatch", note=f"{prev} ran longer than its burst time."), facts

    if c_entry and _key(algo, s_entry) == _key(algo, c_entry):
        return e("tie_breaking"), facts
    if algo in scheduling.USES_PRIORITY and s_entry["priority"] == max(r["priority"] for r in ready):
        return e("priority_direction", local=True), facts
    return e("wrong_selection"), facts


def analyse_scheduling(problem, gantt_rows: list | None, metrics: dict | None) -> dict:
    correct = problem.solve()
    algo = problem.algorithm
    c_tl = correct.timeline()
    errors: list[dict] = []
    segs, fmt_issues = parse_gantt(gantt_rows or [])
    gantt_given = bool(segs)
    s_tl = scheduling.expand_timeline(segs)
    divergence = None
    gantt_correct = gantt_given and s_tl == c_tl and not fmt_issues
    for msg in fmt_issues:
        errors.append(_err("gantt_format", algo, note=msg))

    if gantt_given and not gantt_correct and s_tl != c_tl:
        alt = _alternative_explanations(problem, s_tl)
        local_err, facts = _local_divergence(problem, correct, s_tl, c_tl)
        divergence = facts
        if alt:
            errors.append(_err(alt["type"], algo, whole_chart=True, **alt["detail"]))
        else:
            errors.append(local_err)
        # secondary: total run time per process
        totals: dict[str, int] = {}
        for pid in s_tl:
            if pid != IDLE:
                totals[pid] = totals.get(pid, 0) + 1
        for p in problem.processes:
            if totals.get(p.pid, 0) != p.burst and errors[-1]["type"] != "burst_mismatch":
                errors.append(_err("burst_mismatch", algo, pid=p.pid, ran=totals.get(p.pid, 0), burst=p.burst))

    # ---------------------------------------------------------------- metrics
    own_ct: dict[str, int] = {}
    for s in segs:
        if s.pid != IDLE:
            own_ct[s.pid] = s.end
    first_seg_end: dict[str, int] = {}
    n_segments: dict[str, int] = {}
    for s in correct.gantt:
        if s.pid != IDLE:
            first_seg_end.setdefault(s.pid, s.end)
            n_segments[s.pid] = n_segments.get(s.pid, 0) + 1

    cells: dict[str, dict[str, str]] = {}
    metrics = metrics or {}
    any_metric = False
    for p in problem.processes:
        c = correct.results[p.pid]
        m = metrics.get(p.pid, {}) or {}
        s_ct, s_tat, s_wt = _to_int(m.get("CT")), _to_int(m.get("TAT")), _to_int(m.get("WT"))
        if any(v is not None for v in (s_ct, s_tat, s_wt)):
            any_metric = True
        row: dict[str, str] = {}
        # CT
        if s_ct is None:
            row["CT"] = "missing"
        elif s_ct == c.completion:
            row["CT"] = "correct"
        elif not gantt_correct and own_ct.get(p.pid) == s_ct:
            row["CT"] = "consistent"
        elif n_segments.get(p.pid, 0) > 1 and s_ct == first_seg_end[p.pid]:
            row["CT"] = "wrong"
            errors.append(_err("ct_first_segment", algo, pid=p.pid, student=s_ct, correct=c.completion))
        else:
            row["CT"] = "wrong"
            errors.append(_err("ct_misread", algo, pid=p.pid, student=s_ct, correct=c.completion))
        # TAT
        swapped = s_tat is not None and s_wt is not None and s_tat == c.waiting and s_wt == c.turnaround \
            and c.waiting != c.turnaround
        if s_tat is None:
            row["TAT"] = "missing"
        elif s_tat == c.turnaround:
            row["TAT"] = "correct"
        elif s_ct is not None and s_tat == s_ct - p.arrival:
            row["TAT"] = "consistent"
        elif swapped:
            row["TAT"] = "wrong"
            errors.append(_err("tat_wt_swapped", algo, pid=p.pid))
        elif s_ct is not None and s_tat == s_ct and p.arrival > 0:
            row["TAT"] = "wrong"
            errors.append(_err("tat_forgot_arrival", algo, pid=p.pid, student=s_tat, correct=c.turnaround,
                               ct=s_ct, at=p.arrival))
        else:
            row["TAT"] = "wrong"
            errors.append(_err("arithmetic_tat", algo, pid=p.pid, student=s_tat, correct=c.turnaround))
        # WT
        if s_wt is None:
            row["WT"] = "missing"
        elif s_wt == c.waiting:
            row["WT"] = "correct"
        elif s_tat is not None and s_wt == s_tat - p.burst:
            row["WT"] = "consistent"
        elif swapped:
            row["WT"] = "wrong"
        elif s_tat is not None and s_wt == s_tat:
            row["WT"] = "wrong"
            errors.append(_err("wt_forgot_burst", algo, pid=p.pid, student=s_wt, correct=c.waiting,
                               tat=s_tat, bt=p.burst))
        elif s_wt == c.response and c.response != c.waiting:
            row["WT"] = "wrong"
            errors.append(_err("wt_used_response", algo, pid=p.pid, student=s_wt, correct=c.waiting))
        elif s_ct is not None and s_wt == s_ct - p.burst and p.arrival > 0:
            row["WT"] = "wrong"
            errors.append(_err("wt_forgot_arrival", algo, pid=p.pid, student=s_wt, correct=c.waiting))
        elif s_wt == c.response + p.arrival and p.arrival > 0:
            row["WT"] = "wrong"
            errors.append(_err("wt_used_start", algo, pid=p.pid, student=s_wt, correct=c.waiting))
        else:
            row["WT"] = "wrong"
            errors.append(_err("arithmetic_wt", algo, pid=p.pid, student=s_wt, correct=c.waiting))
        cells[p.pid] = row

    if any_metric:
        for p in problem.processes:
            for k, v in cells[p.pid].items():
                if v == "missing":
                    errors.append(_err("missing_value", algo, pid=p.pid, field=k))

    metrics_correct = any_metric and all(v == "correct" for row in cells.values() for v in row.values())
    observations: dict[str, bool] = {}
    if gantt_given:
        observations[algo] = gantt_correct
    for skill, field in (("CT_READING", "CT"), ("TAT_FORMULA", "TAT"), ("WT_FORMULA", "WT")):
        vals = [cells[p.pid][field] for p in problem.processes if cells[p.pid][field] != "missing"]
        if vals:
            observations[skill] = all(v in ("correct", "consistent") for v in vals)

    return _summarise(errors, {
        "kind": "scheduling",
        "gantt_given": gantt_given,
        "gantt_correct": gantt_correct,
        "metrics_given": any_metric,
        "metrics_correct": metrics_correct,
        "correct": gantt_correct and metrics_correct,
        "divergence": divergence,
        "cells": cells,
        "observations": observations,
        "student_gantt": [(s.pid, s.start, s.end) for s in segs],
    })


# ============================================================================ banker's

def analyse_bankers(problem, student_need: list[list] | None, student_safe: bool | None,
                    student_sequence: list[str] | None) -> dict:
    av, mx, al = problem.available, problem.maximum, problem.allocation
    correct = bankers.safety(av, mx, al)
    need = correct["need"]
    errors: list[dict] = []
    need_cells = None
    need_ok = None
    if student_need is not None:
        sn = [[_to_int(v) for v in row] for row in student_need]
        need_cells = [["correct" if sn[i][j] == need[i][j] else ("missing" if sn[i][j] is None else "wrong")
                       for j in range(len(need[0]))] for i in range(len(need))]
        need_ok = all(c == "correct" for row in need_cells for c in row)
        if not need_ok:
            neg = [[-v for v in row] for row in need]
            added = [[a + b for a, b in zip(r1, r2)] for r1, r2 in zip(mx, al)]
            if sn == neg:
                errors.append(_err("need_sign_error", "BANKERS"))
            elif sn == [list(r) for r in mx]:
                errors.append(_err("need_used_max", "BANKERS"))
            elif sn == added:
                errors.append(_err("need_added", "BANKERS"))
            else:
                bad = [(f"P{i}", problem.resources[j]) for i, row in enumerate(need_cells)
                       for j, c in enumerate(row) if c != "correct"]
                errors.append(_err("need_arithmetic", "BANKERS", cells=bad))

    verdict_ok = None
    seq_check = None
    if student_safe is not None:
        verdict_ok = student_safe == correct["safe"]
        if not verdict_ok:
            errors.append(_err("wrong_safety_verdict", "BANKERS", student=student_safe, correct=correct["safe"]))
    if student_sequence:
        seq_check = bankers.verify_sequence(av, mx, al, student_sequence)
        if not seq_check["valid"]:
            etype = "invalid_sequence"
            if seq_check["error"] == "need_exceeds_work":
                if _sequence_valid_under(av, mx, al, student_sequence, release="need"):
                    etype = "added_need_not_allocation"
                elif _sequence_valid_under(av, mx, al, student_sequence, compare="max"):
                    etype = "compared_max_not_need"
            errors.append(_err(etype, "BANKERS", **seq_check["detail"], fail_step=seq_check["fail_step"],
                               message=seq_check["message"]))

    observations: dict[str, bool] = {}
    if need_ok is not None:
        observations["BANKERS_NEED"] = need_ok
    if verdict_ok is not None:
        observations["BANKERS_SAFETY"] = verdict_ok and (
            not correct["safe"] or (seq_check is not None and seq_check["valid"]))
    correct_all = bool(observations) and all(observations.values()) and need_ok is not None
    return _summarise(errors, {"kind": "bankers", "correct": correct_all, "need_cells": need_cells,
                               "sequence_check": seq_check, "observations": observations,
                               "engine": correct}, first="calculation")


def _sequence_valid_under(av, mx, al, seq, release="allocation", compare="need") -> bool:
    need = bankers.compute_need(mx, al)
    work = list(av)
    try:
        idx = [int(s.strip().upper()[1:]) for s in seq if s.strip()]
    except ValueError:
        return False
    if sorted(idx) != list(range(len(mx))):
        return False
    for k in idx:
        req = need[k] if compare == "need" else mx[k]
        if any(r > w for r, w in zip(req, work)):
            return False
        add = al[k] if release == "allocation" else need[k]
        work = [w + a for w, a in zip(work, add)]
    return True


# ============================================================================ semaphores

def analyse_semaphore(problem, student_final: dict, student_blocked: list[str]) -> dict:
    """Both semaphore definitions used in the course are accepted: the blocking one (value can go negative,
    OSTEP / Silberschatz) and the busy-waiting one from the Module 4 notes (value never below 0)."""
    correct = semaphore.trace(problem.initial, problem.ops)
    busy = {k: max(0, v) for k, v in correct["final_values"].items()}
    errors: list[dict] = []
    values_ok = True
    modes: set[str] = set()
    for sem, cv in correct["final_values"].items():
        sv = _to_int(student_final.get(sem))
        if sv is None:
            values_ok = False
            errors.append(_err("missing_value", "SEMAPHORE", field=sem))
        elif sv == cv or sv == busy[sem]:
            if cv < 0:
                modes.add("blocking" if sv == cv else "busy_wait")
        else:
            values_ok = False
            errors.append(_err("semaphore_count_error", "SEMAPHORE", sem=sem, student=sv, correct=cv,
                               correct_busy_wait=busy[sem]))
    sb = {normalise_pid(p) for p in (student_blocked or []) if str(p).strip()}
    cb = set(correct["blocked"])
    woken = {s["woken"] for s in correct["steps"] if s["woken"]}
    blocked_ok = sb == cb
    if not blocked_ok:
        extra, missing = sb - cb, cb - sb
        if extra & woken:
            errors.append(_err("forgot_wakeup", "SEMAPHORE", processes=sorted(extra & woken)))
        if missing:
            errors.append(_err("missed_block", "SEMAPHORE", processes=sorted(missing)))
        if extra - woken:
            errors.append(_err("missed_block", "SEMAPHORE", wrongly_blocked=sorted(extra - woken)))
    ok = values_ok and blocked_ok
    mode = "mixed" if len(modes) > 1 else (modes.pop() if modes else None)
    return _summarise(errors, {"kind": "semaphore", "correct": ok, "observations": {"SEMAPHORE": ok},
                               "engine": correct, "engine_busy_wait": busy, "semaphore_mode": mode})


# ============================================================================ common

def _summarise(errors: list[dict], result: dict, first: str = "decision") -> dict:
    """Group errors by type and pick the root cause (by default the first decision error, else most frequent)."""
    grouped: dict[str, dict] = {}
    for e in errors:
        g = grouped.setdefault(e["type"], {**{k: e[k] for k in ("type", "category", "skill", "label", "misconception")},
                                           "count": 0, "details": []})
        g["count"] += 1
        g["details"].append(e["detail"])
    rank = {"decision": 0, "calculation": 1, "format": 2} if first == "decision" else \
        {"calculation": 0, "decision": 1, "format": 2}
    order = sorted(grouped.values(), key=lambda g: (rank.get(g["category"], 3), -g["count"]))
    result["errors"] = order
    result["error_types"] = [g["type"] for g in order if g["type"] != "missing_value"]
    result["root_cause"] = next((g for g in order if g["category"] != "format"), order[0] if order else None)
    return result


# ============================================================================ exam-style (I/O bursts, multilevel queues)

def analyse_advanced(problem, metrics: dict | None) -> dict:
    """Cell-by-cell check of CT / TAT / WT for past-paper problems solved by engine.advanced.
    Both waiting-time conventions are accepted (WT = TAT − CPU − I/O, or WT = TAT − CPU) because
    answer keys use both; the analysis says which one the student used."""
    res = problem.solve()
    errors: list[dict] = []
    cells: dict[str, dict[str, str]] = {}
    metrics = metrics or {}
    any_metric = False
    wt_modes: set[str] = set()
    for j in problem.jobs:
        r = res.results[j.pid]
        m = metrics.get(j.pid, {}) or {}
        s_ct, s_tat, s_wt = (_to_float(m.get(k)) for k in ("CT", "TAT", "WT"))
        any_metric = any_metric or any(v is not None for v in (s_ct, s_tat, s_wt))
        row = {}
        row["CT"] = "missing" if s_ct is None else "correct" if _eq(s_ct, r.completion) else "wrong"
        if row["CT"] == "wrong":
            errors.append(_err("ct_misread", "ADVANCED", pid=j.pid, student=s_ct, correct=r.completion))
        if s_tat is None:
            row["TAT"] = "missing"
        elif _eq(s_tat, r.turnaround):
            row["TAT"] = "correct"
        elif s_ct is not None and _eq(s_tat, s_ct - j.arrival):
            row["TAT"] = "consistent"
        elif s_ct is not None and _eq(s_tat, s_ct) and j.arrival > 0:
            row["TAT"] = "wrong"
            errors.append(_err("tat_forgot_arrival", "ADVANCED", pid=j.pid, student=s_tat, correct=r.turnaround))
        else:
            row["TAT"] = "wrong"
            errors.append(_err("arithmetic_tat", "ADVANCED", pid=j.pid, student=s_tat, correct=r.turnaround))
        if s_wt is None:
            row["WT"] = "missing"
        elif _eq(s_wt, r.waiting) or _eq(s_wt, r.waiting_incl_io):
            row["WT"] = "correct"
            if j.io:
                wt_modes.add("excludes I/O" if _eq(s_wt, r.waiting) else "counts I/O as waiting")
        elif s_tat is not None and (_eq(s_wt, s_tat - j.cpu - j.io) or _eq(s_wt, s_tat - j.cpu)):
            row["WT"] = "consistent"
        elif s_tat is not None and _eq(s_wt, s_tat):
            row["WT"] = "wrong"
            errors.append(_err("wt_forgot_burst", "ADVANCED", pid=j.pid, student=s_wt, correct=r.waiting))
        else:
            row["WT"] = "wrong"
            errors.append(_err("arithmetic_wt", "ADVANCED", pid=j.pid, student=s_wt, correct=r.waiting))
        cells[j.pid] = row
    if any_metric:
        for pid, row in cells.items():
            for k, v in row.items():
                if v == "missing":
                    errors.append(_err("missing_value", "ADVANCED", pid=pid, field=k))
    observations = {}
    for skill, field in (("CT_READING", "CT"), ("TAT_FORMULA", "TAT"), ("WT_FORMULA", "WT")):
        vals = [cells[j.pid][field] for j in problem.jobs if cells[j.pid][field] != "missing"]
        if vals:
            observations[skill] = all(v in ("correct", "consistent") for v in vals)
    correct = any_metric and all(v == "correct" for row in cells.values() for v in row.values())
    return _summarise(errors, {"kind": "advanced", "correct": correct, "cells": cells, "metrics_given": any_metric,
                               "metrics_correct": correct, "gantt_given": False, "gantt_correct": None,
                               "observations": observations, "wt_modes": sorted(wt_modes), "divergence": None},
                      first="calculation")


def _to_float(x):
    v = _to_int(x)
    return None if v is None else float(v)


def _eq(a, b) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) < 0.011
