"""
Teaching strategy: plain, inspectable rules decide WHAT the tutor does next.
The LLM only decides HOW to say it.

Small models are unreliable at multi-step pedagogical decisions, so this layer is
deterministic. It also controls what the LLM is allowed to know: when the student
should still find the answer themselves, the correct answer is simply left out of
the facts given to the LLM, so it cannot leak it.

Hint ladder (escalates with wrong submissions + hint requests on the same problem):
    0-1  SOCRATIC_HINT     a guiding question about the first mistake
    2    TARGETED_HINT     the relevant facts (ready queue, remaining times), no answer
    3+   REVEAL_STEP       the correct step and the engine's reason
Overrides:
    correct answer               -> CONFIRM_AND_EXTEND (short praise + a "why" question)
    whole chart = wrong rule     -> ALGORITHM_REMINDER (contrast the two rules)
    numbers wrong, chart right   -> FORMULA_REMINDER
    recurring misconception      -> WORKED_EXAMPLE (engine-generated mini example)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from engine import bankers, scheduling, semaphore
from engine.generator import SchedulingProblem
from engine.scheduling import ALGORITHMS, IDLE, Process

RULES = {
    "FCFS": "FCFS runs processes in order of arrival; it is non-preemptive.",
    "SJF": "SJF picks, among the processes that have ARRIVED, the one with the shortest burst time; once started it runs to completion.",
    "SRTF": "SRTF always runs the arrived process with the shortest REMAINING time; whenever a process arrives, compare it with the running one and preempt only if it is strictly shorter.",
    "RR": "Round Robin takes the process at the front of a FIFO ready queue and runs it for at most one time quantum; if it is not finished it goes to the back of the queue (after any process that arrived by then).",
    "PRIORITY_NP": "Non-preemptive priority picks the arrived process with the highest priority (LOWEST number) and runs it to completion.",
    "PRIORITY_P": "Preemptive priority always runs the arrived process with the highest priority (LOWEST number); a newly arrived process preempts only if its priority is strictly higher.",
    "BANKERS": "Need = Max − Allocation. A process can finish if Need ≤ Work; when it finishes, Work = Work + its Allocation. The state is safe if all processes can finish in some order.",
    "SEMAPHORE": "wait(S): S = S − 1, and the caller blocks if S < 0. signal(S): S = S + 1, and if S ≤ 0 one waiting process (FIFO) is woken.",
}
FORMULAS = {
    "CT_READING": "Completion time (CT) = the time the process finishes its LAST run in the Gantt chart.",
    "TAT_FORMULA": "Turnaround time: TAT = CT − AT (arrival time).",
    "WT_FORMULA": "Waiting time: WT = TAT − BT (burst time) = CT − AT − BT.",
    "BANKERS_NEED": "Need = Max − Allocation, cell by cell.",
}
COMPARE_WITH = {"FCFS": "SJF", "SJF": "SRTF", "SRTF": "RR", "RR": "FCFS", "PRIORITY_NP": "PRIORITY_P", "PRIORITY_P": "PRIORITY_NP"}


@dataclass
class Strategy:
    action: str
    reveal: bool
    level: str
    instruction: str
    facts: list[str] = field(default_factory=list)
    focus: str | None = None
    rationale: str = ""
    escalation: int = 0
    secrets: dict = field(default_factory=lambda: {"pids": [], "numbers": []})
    worked_example: dict | None = None
    topic: str = ""
    retrieval_query: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _proc_line(problem) -> str:
    if getattr(problem, "kind", "scheduling") != "scheduling":
        return problem.statement()
    pri = problem.algorithm in scheduling.USES_PRIORITY
    procs = ", ".join(f"{p.pid}(AT={p.arrival}, BT={p.burst}" + (f", priority={p.priority}" if pri else "") + ")"
                      for p in problem.processes)
    q = f", time quantum {problem.quantum}" if problem.algorithm == "RR" else ""
    return f"{ALGORITHMS[problem.algorithm]}{q}. Processes: {procs}."


def _ready_line(ready: list[dict], algo: str) -> str:
    parts = []
    for r in ready:
        if algo in ("SRTF", "RR"):
            parts.append(f"{r['pid']} (remaining {r['remaining']}, arrived {r['arrival']})")
        elif algo in scheduling.USES_PRIORITY:
            parts.append(f"{r['pid']} (priority {r['priority']}, remaining {r['remaining']})")
        elif algo == "SJF":
            parts.append(f"{r['pid']} (burst {r['burst']})")
        else:
            parts.append(f"{r['pid']} (arrived {r['arrival']})")
    return ", ".join(parts) if parts else "none"


def decide(problem, analysis: dict | None, level: str, recurring: list[dict], attempt_no: int,
           hints_used: int) -> Strategy:
    kind = getattr(problem, "kind", "scheduling")
    if kind == "advanced":
        return _advanced_strategy(problem, analysis, level, max(0, attempt_no - 1) + hints_used)
    topic = problem.algorithm if kind == "scheduling" else kind.upper()
    escalation = max(0, attempt_no - 1) + hints_used
    base_facts = [f"Problem: {_proc_line(problem)}", f"Rule: {RULES[topic]}"]

    if analysis is None:
        return _start_hint(problem, topic, level, base_facts, escalation)
    if analysis.get("correct"):
        return _confirm(problem, topic, level, base_facts)

    root = analysis.get("root_cause")
    rtype = root["type"] if root else None
    recurring_types = {r["type"]: r for r in recurring}
    if rtype in recurring_types and escalation <= 2 and kind == "scheduling":
        return _worked_example(problem, topic, level, base_facts, root, recurring_types[rtype], analysis)

    if kind == "bankers":
        return _bankers_strategy(problem, analysis, level, base_facts, escalation)
    if kind == "semaphore":
        return _semaphore_strategy(problem, analysis, level, base_facts, escalation)

    if root and root["category"] == "decision" and root["details"] and root["details"][0].get("whole_chart"):
        return _algorithm_reminder(problem, topic, level, base_facts, root, analysis, escalation)
    if analysis.get("gantt_given") and not analysis.get("gantt_correct"):
        return _gantt_hint(problem, topic, level, base_facts, root, analysis, escalation)
    return _formula_hint(problem, topic, level, base_facts, analysis, escalation)


# ------------------------------------------------------------------ individual strategies

def _start_hint(problem, topic, level, facts, escalation) -> Strategy:
    if getattr(problem, "kind", "scheduling") != "scheduling":
        return Strategy("START_HINT", False, level,
                        "The student has not answered yet and asked how to start. Explain the first step only, "
                        "using the rule. Do not solve the problem.", facts, rationale="Hint requested before any attempt.",
                        escalation=escalation, topic=topic)
    res = problem.solve()
    first = next(d for d in res.decisions)
    facts = facts + [f"At t={first.time} the arrived processes are: {_ready_line(first.ready, topic) if first.ready else 'none (CPU idle)'}."]
    reveal = escalation >= 2
    if reveal:
        facts.append(f"Engine decision at t={first.time}: {first.reason}")
        instr = "Explain the first scheduling decision and why, then tell the student to continue the Gantt chart."
    else:
        instr = ("The student asked how to start. Ask them which processes have arrived at the first decision point "
                 "and how the rule chooses between them. Do not name the process that runs first.")
    return Strategy("START_HINT", reveal, level, instr, facts, rationale="Hint requested before any attempt.",
                    escalation=escalation, secrets={"pids": [] if reveal else [first.chosen], "numbers": []}, topic=topic)


def _confirm(problem, topic, level, facts) -> Strategy:
    if getattr(problem, "kind", "scheduling") == "scheduling":
        res = problem.solve()
        other = COMPARE_WITH[topic]
        alt = scheduling.run(other, problem.processes, problem.quantum or 2)
        facts = facts + [f"The student's answer is fully correct. Average WT = {res.avg_wt:.2f}, average TAT = {res.avg_tat:.2f}.",
                         f"For comparison, {ALGORITHMS[other]} on the same processes gives average WT = {alt.avg_wt:.2f}."]
        instr = (f"Congratulate the student in one short sentence. Then ask ONE thought-provoking question: why does "
                 f"{ALGORITHMS[other]} give a {'lower' if alt.avg_wt < res.avg_wt else 'higher or equal'} average waiting "
                 f"time here? Do not answer the question.")
    else:
        facts = facts + ["The student's answer is fully correct."]
        instr = "Congratulate the student in one short sentence and ask one 'why' question that deepens understanding."
    return Strategy("CONFIRM_AND_EXTEND", True, level, instr, facts, rationale="Answer verified correct by the OS Engine.",
                    topic=topic)


def _worked_example(problem, topic, level, facts, root, rec, analysis) -> Strategy:
    skill = root.get("skill")
    algo = "FCFS" if skill in ("CT_READING", "TAT_FORMULA", "WT_FORMULA") else topic
    mini = _mini_example(algo)
    res = mini.solve()
    lines = [f"Worked example ({ALGORITHMS[algo]}{', q=' + str(mini.quantum) if mini.quantum else ''}): "
             + ", ".join(f"{p.pid}(AT={p.arrival}, BT={p.burst}" + (f", pr={p.priority}" if algo in scheduling.USES_PRIORITY else "") + ")"
                         for p in mini.processes)]
    lines.append("Gantt chart: " + " | ".join(f"{s.pid} {s.start}-{s.end}" for s in res.gantt))
    for d in res.decisions:
        if d.kind != "idle":
            lines.append(f"  t={d.time}: {d.reason}")
    for p in mini.processes:
        r = res.results[p.pid]
        lines.append(f"  {p.pid}: CT={r.completion}, TAT={r.completion}−{p.arrival}={r.turnaround}, "
                     f"WT={r.turnaround}−{p.burst}={r.waiting}")
    facts = facts + [f"This mistake has now appeared in {rec['count']} different recent problems: {root['label']}.",
                     f"Misconception: {root.get('misconception') or root['label']}"] + lines
    instr = ("The student keeps making the same mistake. Do NOT talk about their current problem's answer. Walk through "
             "the worked example step by step (it is short), highlighting exactly the step related to the misconception. "
             "Finish by asking the student to retry their original problem.")
    return Strategy("WORKED_EXAMPLE", False, level, instr, facts, focus=root["type"],
                    rationale=f"Recurring misconception (seen in {rec['count']} different recent problems) → switch from hints to a "
                              f"worked example, which works better than repeated hints for a persistent error.",
                    secrets=_scheduling_secrets(problem, analysis), worked_example=mini.to_dict(), topic=topic)


def _mini_example(algo: str) -> SchedulingProblem:
    P = Process
    examples = {
        "FCFS": [P("A", 0, 3), P("B", 1, 4), P("C", 2, 2)],
        "SJF": [P("A", 0, 4), P("B", 1, 5), P("C", 2, 1)],
        "SRTF": [P("A", 0, 5), P("B", 1, 2), P("C", 2, 4)],
        "RR": [P("A", 0, 4), P("B", 1, 3), P("C", 2, 2)],
        "PRIORITY_NP": [P("A", 0, 3, 3), P("B", 1, 2, 1), P("C", 2, 2, 2)],
        "PRIORITY_P": [P("A", 0, 4, 3), P("B", 1, 2, 1), P("C", 2, 2, 2)],
    }
    return SchedulingProblem(algo, 1, examples[algo], 2 if algo == "RR" else None, seed=0)


def _scheduling_secrets(problem, analysis) -> dict:
    res = problem.solve()
    nums: set[int] = set()
    values = []           # which quantity each hidden number is, so the guard can judge numbers that also appear as data
    for pid, row in (analysis.get("cells") or {}).items():
        r = res.results[pid]
        for k, v in row.items():
            if v == "wrong":
                n = {"CT": r.completion, "TAT": r.turnaround, "WT": r.waiting}[k]
                nums.add(n)
                values.append({"pid": pid, "field": k, "value": n})
    div = analysis.get("divergence") or {}
    pids = [div["correct_pid"]] if div.get("correct_pid") and div.get("correct_pid") != IDLE else []
    return {"pids": pids, "numbers": sorted(nums), "values": values}


def _algorithm_reminder(problem, topic, level, facts, root, analysis, escalation) -> Strategy:
    det = root["details"][0]
    t = root["type"]
    if t == "algorithm_confusion":
        other = det["applied"]
        what = f"The student's entire Gantt chart is exactly what {ALGORITHMS[other]} would produce, not {ALGORITHMS[topic]}."
        extra = [f"Rule of {ALGORITHMS[other]}: {RULES[other]}"]
    elif t == "priority_direction":
        what = "The student's chart matches treating a LARGER number as higher priority. In this course a LOWER number means higher priority."
        extra = []
    elif t == "rr_requeue_order":
        what = ("The student's chart matches putting the preempted process back in the queue BEFORE a process that "
                "arrived at the same moment. The convention here: new arrivals join first, then the preempted process.")
        extra = []
    else:
        what = f"The student's chart matches Round Robin with quantum {det.get('used_quantum')} instead of {det.get('correct_quantum')}."
        extra = []
    div = analysis.get("divergence") or {}
    facts = facts + [what] + extra
    if div:
        facts.append(f"The first point where the student's chart differs is t={div['time']}.")
    reveal = escalation >= 3
    if reveal and div:
        facts.append(f"At t={div['time']} the correct choice is {div['correct_pid']}. Engine reason: {div.get('correct_reason') or ''}")
    instr = ("Explain the key difference between the rule the student applied and the correct rule in 2-3 sentences, "
             "then ask them to redo the chart from the first point where it differs."
             + ("" if reveal else " Do not give the correct process or numbers."))
    return Strategy("ALGORITHM_REMINDER", reveal, level, instr, facts, focus=t,
                    rationale="Whole chart matches a different rule → the problem is the rule, not one step.",
                    escalation=escalation, secrets={} if reveal else _scheduling_secrets(problem, analysis), topic=topic)


def _gantt_hint(problem, topic, level, facts, root, analysis, escalation) -> Strategy:
    div = analysis["divergence"]
    t0 = div["time"]
    f = facts + [f"The student's Gantt chart is correct up to t={t0}.",
                 f"At t={t0} the student scheduled {div['student_pid']}.",
                 f"Detected error type: {root['label']}."]
    if escalation <= 1:
        action, reveal = "SOCRATIC_HINT", False
        instr = (f"Ask ONE guiding question that makes the student re-check the decision at t={t0} using the rule. "
                 f"Do not say which process should run and do not give any numbers they have to compute.")
    elif escalation == 2:
        action, reveal = "TARGETED_HINT", False
        prev = div.get("running_before")
        f.append(f"Processes ready at t={t0}: {_ready_line(div['ready'], topic)}."
                 + (f" {prev} was running just before t={t0}." if prev and prev != IDLE else ""))
        if div.get("queue"):
            f.append(f"Ready queue order at t={t0} (front first): {', '.join(div['queue'])}.")
        instr = (f"Point the student to the ready processes at t={t0} listed in FACTS and ask them to apply the rule to "
                 f"them. Do not name the process that should run.")
    else:
        action, reveal = "REVEAL_STEP", True
        f.append(f"Processes ready at t={t0}: {_ready_line(div['ready'], topic)}.")
        f.append(f"Correct choice at t={t0}: {div['correct_pid']}. Engine reason: {div.get('correct_reason') or RULES[topic]}")
        instr = (f"Explain which process should run at t={t0} and why, using the engine reason. Then ask the student to "
                 f"continue the Gantt chart from t={t0} themselves.")
    if root.get("misconception"):
        f.append(f"Likely misconception: {root['misconception']}")
    return Strategy(action, reveal, level, instr, f, focus=root["type"],
                    rationale=f"Gantt chart wrong; hint level {escalation} (wrong submissions + hints on this problem).",
                    escalation=escalation, secrets={} if reveal else _scheduling_secrets(problem, analysis), topic=topic)


def _formula_hint(problem, topic, level, facts, analysis, escalation) -> Strategy:
    errs = [e for e in analysis["errors"] if e["category"] == "calculation"]
    if not errs:
        return Strategy("ASK_TO_COMPLETE", False, level,
                        "Tell the student their answer is incomplete and ask them to fill in the missing parts.",
                        facts + ["Some required values are missing."], rationale="Answer incomplete.", topic=topic)
    e = errs[0]
    pids = [d.get("pid") for d in e["details"] if d.get("pid")]
    by_id = {p.pid: p for p in problem.processes}
    res = problem.solve()
    chart = "The Gantt chart is correct." if analysis.get("gantt_given") else \
        "The student gave no Gantt chart, only values (drawing the chart first helps)."
    f = facts + [chart, f"Detected error: {e['label']} (processes: {', '.join(pids)})."]
    if e.get("skill") in FORMULAS:
        f.append(f"Formula: {FORMULAS[e['skill']]}")
    if e.get("misconception"):
        f.append(f"Likely misconception: {e['misconception']}")
    first = pids[0] if pids else None
    reveal = escalation >= 3
    if first:
        p = by_id[first]
        field = {"CT_READING": "CT", "TAT_FORMULA": "TAT", "WT_FORMULA": "WT"}.get(e.get("skill"), "value")
        student_val = e["details"][0].get("student")
        f.append(f"For {first}: AT={p.arrival}, BT={p.burst}"
                 + (f"; the student wrote {field}={student_val}." if student_val is not None else "."))
        if reveal:
            r = res.results[first]
            f.append(f"Correct for {first}: CT={r.completion}, TAT={r.completion}−{p.arrival}={r.turnaround}, "
                     f"WT={r.turnaround}−{p.burst}={r.waiting}.")
    instr = ("Remind the student of the formula in FACTS and ask them to recompute the value for "
             f"{first or 'the marked processes'} themselves. Do not give the correct number." if not reveal else
             f"Show the correct calculation for {first} step by step using FACTS, then ask the student to fix the others.")
    return Strategy("FORMULA_REMINDER", reveal, level, instr, f, focus=e["type"],
                    rationale="Gantt chart right but numbers wrong → calculation error, not a scheduling error.",
                    escalation=escalation, secrets={} if reveal else _scheduling_secrets(problem, analysis), topic=topic)


def _bankers_strategy(problem, analysis, level, facts, escalation) -> Strategy:
    root = analysis["root_cause"]
    eng = analysis["engine"]
    f = facts + [f"Available = {problem.available}, resources {problem.resources}.",
                 f"Detected error: {root['label']}."]
    if root.get("misconception"):
        f.append(f"Likely misconception: {root['misconception']}")
    secrets = {"pids": [], "numbers": []}
    reveal = escalation >= 3
    if root["skill"] == "BANKERS_NEED":
        f.append(f"Formula: {FORMULAS['BANKERS_NEED']}")
        if reveal:
            f.append("Correct Need matrix: " + "; ".join(f"P{i}={row}" for i, row in enumerate(eng["need"])))
        instr = ("Remind the student how Need is computed and ask them to recompute the matrix." if not reveal else
                 "Show the correct Need matrix and explain one row as an example.")
        action = "FORMULA_REMINDER"
    else:
        det = root["details"][0] if root["details"] else {}
        if det.get("fail_step"):
            f.append(f"The student's sequence fails at step {det['fail_step']}: {det.get('message', '')}")
        if escalation >= 2:
            f.append("Engine safety trace: " + " → ".join(
                f"{s['process']} (Need {s['need']} ≤ Work {s['work_before']}, Work becomes {s['work_after']})"
                for s in eng["steps"][:max(1, det.get('fail_step', 1) or 1)]))
        if reveal:
            f.append("Engine result: " + ("safe, sequence " + ", ".join(eng["sequence"]) if eng["safe"]
                                          else "UNSAFE; stuck processes " + ", ".join(eng["stuck"])))
        else:
            secrets["pids"] = []
        instr = ("Ask the student to re-check the Need ≤ Work comparison at the failing step and how Work changes "
                 "after a process finishes. Do not give a safe sequence." if not reveal else
                 "Walk through the engine's safety trace and explain the verdict.")
        action = "REVEAL_STEP" if reveal else ("TARGETED_HINT" if escalation == 2 else "SOCRATIC_HINT")
    return Strategy(action, reveal, level, instr, f, focus=root["type"], escalation=escalation,
                    rationale="Banker's answer checked by simulating the student's sequence.", secrets=secrets,
                    topic="BANKERS")


def _semaphore_strategy(problem, analysis, level, facts, escalation) -> Strategy:
    root = analysis["root_cause"]
    eng = analysis["engine"]
    f = facts + [f"Detected error: {root['label']}."]
    if root.get("misconception"):
        f.append(f"Likely misconception: {root['misconception']}")
    reveal = escalation >= 3
    if escalation >= 2:
        f.append("Engine trace: " + "; ".join(
            f"{s['step']}. {s['pid']}: {s['op']}({s['sem']}) → {s['sem']}={s['value_after']}"
            + ("" if not reveal else f" [{s['effect']}]") for s in eng["steps"]))
    if reveal:
        f.append(f"Final values: {eng['final_values']}; blocked at end: {eng['blocked'] or 'none'}.")
    secrets = {"pids": [], "numbers": [] if reveal else list(eng["final_values"].values())}
    instr = ("Ask the student to trace the value after each operation and to note who blocks and who is woken. "
             "Do not give the final value." if not reveal else
             "Walk through the trace and explain the final value and blocked processes.")
    action = "REVEAL_STEP" if reveal else ("TARGETED_HINT" if escalation == 2 else "SOCRATIC_HINT")
    return Strategy(action, reveal, level, instr, f, focus=root["type"], escalation=escalation,
                    rationale="Semaphore answer checked against the engine trace.", secrets=secrets, topic="SEMAPHORE")


def _advanced_strategy(problem, analysis, level, escalation) -> Strategy:
    """Past-paper questions with I/O bursts or multilevel queues: formula-level feedback."""
    res = problem.solve()
    facts = [f"Problem: {problem.statement()}",
             "Formulas: TAT = CT − AT. WT = TAT − (all CPU bursts) − (all I/O bursts); some answer keys count I/O "
             "as waiting, i.e. WT = TAT − CPU. Both are accepted if used consistently."]
    if problem.queues:
        facts.append("Multilevel queue rule: a lower queue runs only when all higher queues are empty; an arrival in a "
                     "higher queue preempts a lower one.")
    if problem.has_io():
        facts.append("I/O rule: during a process's I/O burst it is not in the ready queue; when the I/O finishes it "
                     "re-enters the ready queue at that time.")
    if analysis is None:
        first = res.gantt[0]
        reveal = escalation >= 2
        if reveal:
            facts.append(f"The first block of the Gantt chart is {first[0]} from {first[1]:g} to {first[2]:g}.")
        return Strategy("START_HINT", reveal, level,
                        "Explain how to start this exam-style problem (the rules above). "
                        + ("Then describe the first Gantt block." if reveal else "Do not give any numbers."),
                        facts, rationale="Hint requested before any attempt.", escalation=escalation, topic="ADVANCED")
    if analysis.get("correct"):
        facts.append(f"All values are correct. Average WT = {res.avg('waiting'):.2f}"
                     + (f" (or {res.avg('waiting_incl_io'):.2f} if I/O is counted as waiting)" if problem.has_io() else "")
                     + f", average TAT = {res.avg('turnaround'):.2f}.")
        return Strategy("CONFIRM_AND_EXTEND", True, level,
                        "Congratulate briefly and ask one question about why the order of execution came out this way.",
                        facts, rationale="Answer verified by the OS Engine.", topic="ADVANCED")
    wrong = [(pid, k) for pid, row in analysis["cells"].items() for k, v in row.items() if v == "wrong"]
    pids = sorted({p for p, _ in wrong})
    root = analysis.get("root_cause")
    facts.append(f"Wrong cells: {', '.join(f'{k} of {p}' for p, k in wrong) or 'none'}.")
    if root:
        facts.append(f"Most likely issue: {root['label']}. {root.get('misconception') or ''}")
    reveal = escalation >= 2
    if reveal and pids:
        r = res.results[pids[0]]
        facts.append(f"Correct values for {pids[0]}: CT = {r.completion:g}, TAT = {r.turnaround:g}, WT = {r.waiting:g} "
                     f"(or {r.waiting_incl_io:g} counting I/O as waiting).")
        facts.append("Gantt chart: " + " | ".join(f"{p} {a:g}-{b:g}" for p, a, b in res.gantt))
    instr = ("Point out which cells are wrong and remind the student of the relevant rule; do not give correct values."
             if not reveal else "Show the correct values for the first wrong process and the Gantt chart, then ask the "
                                "student to fix the remaining cells.")
    return Strategy("REVEAL_STEP" if reveal else "FORMULA_REMINDER", reveal, level, instr, facts,
                    focus=root["type"] if root else None, rationale="Exam-style problem: checked cell by cell.",
                    escalation=escalation, topic="ADVANCED",
                    secrets={"pids": [], "numbers": [] if reveal else sorted({int(res.results[p].completion) for p in pids})})
