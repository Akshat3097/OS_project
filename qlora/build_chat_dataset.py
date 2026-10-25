"""
Chat-style fine-tuning data: how the tutor should talk when a student chats with it directly
(e.g. `ollama run os-tutor`), with no app around it.

Every number in these examples comes from the OS Engine, and every explanation from the lessons or
the class notes, so the model is trained only on verified content. Kinds of example:

  explain    concept explanations (everyday example first, then the rule, then a check question)
  differently  "explain it differently" follow-ups
  quiz       multi-turn MCQ quizzes with feedback
  teachback  the student explains a topic; the tutor says what was right, what is missing, fixes misconceptions
  notes      questions answered from the class notes (with module and slide numbers)
  solve      worked solutions: scheduling (6 algorithms), Banker's safety and requests, semaphore traces
  check      the student shows an answer; the tutor finds the first mistake and hints (then reveals if asked)
  handwritten  misconceptions, conventions, exam advice, scope

    python -m qlora.build_chat_dataset            # writes qlora/data/chat_{train,val}.jsonl and {train,val}_all.jsonl
    python -m qlora.build_chat_dataset --student-frac 0.4 --out qlora/data/v2
                                                  # v2: plus student-style copies (qlora/student_style.py)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path

from engine import bankers, generator, question_bank, scheduling, semaphore
from engine.scheduling import IDLE, Process
from qlora.chat_style import CHAT_SYSTEM
from qlora.student_style import student_variants
from tutor import teachback
from tutor.lessons import LESSONS

HERE = Path(__file__).resolve().parent
OUT = HERE / "data"
SOURCES = HERE.parent / "rag" / "sources"

ALGOS = ["FCFS", "SJF", "SRTF", "RR", "PRIORITY_NP", "PRIORITY_P"]
SAY = {"FCFS": ["FCFS", "first come first serve", "FCFS scheduling"],
       "SJF": ["SJF", "non-preemptive SJF", "shortest job first (non-preemptive)"],
       "SRTF": ["SRTF", "preemptive SJF", "shortest remaining time first"],
       "RR": ["round robin", "RR", "Round Robin"],
       "PRIORITY_NP": ["non-preemptive priority", "priority scheduling (non-preemptive)"],
       "PRIORITY_P": ["preemptive priority", "priority scheduling (preemptive)"]}
NAME = {"FCFS": "FCFS", "SJF": "non-preemptive SJF", "SRTF": "SRTF", "RR": "Round Robin",
        "PRIORITY_NP": "non-preemptive priority", "PRIORITY_P": "preemptive priority"}
CLOSERS = {
    "FCFS": ["Which process here suffers most from the convoy effect?",
             "How would the average waiting time change if the shortest process had arrived first?"],
    "SJF": ["Which process could starve if short jobs kept arriving?",
            "How would SRTF change this schedule?"],
    "SRTF": ["Where did a preemption happen, and why exactly then?",
             "Would non-preemptive SJF give a different first decision here?"],
    "RR": ["What would change if the quantum were larger than every burst?",
           "Which process waited longest in the queue, and why?"],
    "PRIORITY_NP": ["Which process could starve here, and what fixes that?",
                    "What changes if a high-priority process arrives while a low one is running?"],
    "PRIORITY_P": ["Which process could starve here, and what fixes that?",
                   "Where did a preemption happen, and why?"],
}


def fmt(x) -> str:
    x = round(float(x), 2)
    return str(int(x)) if x.is_integer() else f"{x:g}"


def msgs(*turns: str) -> list[dict]:
    out = [{"role": "system", "content": CHAT_SYSTEM}]
    for i, t in enumerate(turns):
        out.append({"role": "user" if i % 2 == 0 else "assistant", "content": t.strip()})
    return out


# ============================================================================ scheduling
def priority_dir(lower: bool) -> str:
    return "lower number = higher priority" if lower else "higher number = higher priority"


def problem_text(algo: str, procs: list[Process], q: int | None, lower: bool, rng: random.Random,
                 state_dir: bool = True) -> str:
    pri = algo.startswith("PRIORITY")
    say = rng.choice(SAY[algo]) + (f" (q = {q})" if q else "")
    style = rng.randrange(4)
    if style == 0:
        rows = ", ".join(f"{p.pid} AT={p.arrival} BT={p.burst}" + (f" priority={p.priority}" if pri else "") for p in procs)
        body = f"Solve using {say}: {rows}."
    elif style == 1:
        head = "Process AT BT" + (" Priority" if pri else "")
        rows = "\n".join(f"{p.pid} {p.arrival} {p.burst}" + (f" {p.priority}" if pri else "") for p in procs)
        body = f"Find the average waiting time and turnaround time with {say}.\n{head}\n{rows}"
    elif style == 2:
        rows = " ".join(f"{p.pid}({p.arrival},{p.burst}" + (f",{p.priority}" if pri else "") + ")" for p in procs)
        fields = "(arrival, burst" + (", priority)" if pri else ")")
        body = f"{say}: {rows} {fields}. Draw the Gantt chart and find CT, TAT and WT."
    else:
        rows = "; ".join(f"{p.pid} arrives at {p.arrival} and needs {p.burst} ms" + (f" with priority {p.priority}" if pri else "")
                         for p in procs)
        body = f"Can you schedule these with {say}? {rows}."
    if pri and (state_dir or not lower):
        body += f" ({priority_dir(lower).capitalize()}.)"
    return body


def rule_line(algo: str, q: int | None, lower: bool) -> str:
    d = priority_dir(lower)
    return {"FCFS": "FCFS runs processes in order of arrival, each one to completion.",
            "SJF": "Non-preemptive SJF: whenever the CPU is free, pick the arrived process with the smallest burst and run "
                   "it to completion; ties go to the earlier arrival.",
            "SRTF": "SRTF: at every arrival compare remaining times. The shortest remaining time runs, and a running "
                    "process is preempted only if a newcomer is strictly shorter.",
            "RR": f"Round Robin with q = {q}: run the front of the FIFO ready queue for at most {q} units; an unfinished "
                  f"process goes to the back, and a process arriving when a slice ends joins the queue before it.",
            "PRIORITY_NP": f"Non-preemptive priority ({d}): when the CPU is free, pick the highest-priority arrived process "
                           f"and run it to completion; ties go to the earlier arrival.",
            "PRIORITY_P": f"Preemptive priority ({d}): the highest-priority ready process runs, and a newcomer preempts it "
                          f"only if its priority is strictly higher."}[algo]


def gantt_text(gantt) -> str:
    return " → ".join(f"[{fmt(s.start)}–{fmt(s.end)}] {'idle' if s.pid == IDLE else s.pid}" for s in gantt)


def table_text(res, show_rt: bool) -> str:
    head = "| Process | AT | BT | CT | TAT | WT |" + (" RT |" if show_rt else "")
    sep = "|---|---|---|---|---|---|" + ("---|" if show_rt else "")
    rows = [f"| {r.pid} | {r.arrival} | {r.burst} | {r.completion} | {r.turnaround} | {r.waiting} |"
            + (f" {r.response} |" if show_rt else "") for r in res.results.values()]
    return "\n".join([head, sep, *rows])


def averages(res) -> str:
    rs = list(res.results.values())
    n = len(rs)
    tat = " + ".join(str(r.turnaround) for r in rs)
    wt = " + ".join(str(r.waiting) for r in rs)
    return (f"Average TAT = ({tat}) / {n} = {fmt(res.avg_tat)}\n"
            f"Average WT = ({wt}) / {n} = {fmt(res.avg_wt)}")


def steps_text(res, limit: int = 14) -> str:
    lines = []
    for d in res.decisions:
        if d.kind == "idle":
            lines.append(f"- t = {d.time}: no process is ready, so the CPU is idle until the next arrival.")
        else:
            lines.append(f"- t = {d.time}: {d.reason}")
    if len(lines) > limit:
        lines = lines[:limit] + ["- … the same rule continues until every process finishes."]
    return "\n".join(lines)


def solution_text(algo, procs, q, lower, res, rng, stated_dir: bool) -> str:
    parts = []
    if algo.startswith("PRIORITY") and not stated_dir:
        parts.append("I'll take a lower number as higher priority, as your class notes do.")
    parts.append(f"**Rule.** {rule_line(algo, q, lower)}")
    parts.append(f"**Decisions**\n{steps_text(res)}")
    parts.append(f"**Gantt chart:** {gantt_text(res.gantt)}")
    parts.append(f"**Table** (TAT = CT − AT, WT = TAT − BT)\n{table_text(res, rng.random() < 0.35)}")
    parts.append(averages(res))
    parts.append(rng.choice(CLOSERS[algo]))
    return "\n\n".join(parts)


def scheduling_examples(rng: random.Random, n_per_algo: int) -> list[dict]:
    out = []
    for algo in ALGOS:
        for k in range(n_per_algo):
            diff = 1 + k % 3
            prob = generator.generate_scheduling(algo, diff, seed=rng.randrange(10**9))
            lower = True
            if algo.startswith("PRIORITY") and rng.random() < 0.2:
                lower = False
            res = scheduling.run(algo, prob.processes, prob.quantum, **({"lower_is_higher": lower} if algo.startswith("PRIORITY") else {}))
            stated = not algo.startswith("PRIORITY") or not lower or rng.random() < 0.7
            user = problem_text(algo, prob.processes, prob.quantum, lower, rng, state_dir=stated)
            out.append({"kind": "solve", "messages": msgs(user, solution_text(algo, prob.processes, prob.quantum, lower, res, rng, stated))})
    return out


# ---------------------------------------------------------------- checking a student's answer
def answer_text(res, metrics: dict, gantt=None, rng=None) -> str:
    parts = []
    if gantt:
        parts.append("Gantt: " + " | ".join(f"{p} {a}-{b}" for p, a, b in gantt))
    rows = "; ".join(f"{pid}: CT {m['CT']}, TAT {m['TAT']}, WT {m['WT']}" for pid, m in metrics.items())
    parts.append(rows)
    return "\n".join(parts)


def check_examples(rng: random.Random, n: int) -> list[dict]:
    out = []
    kinds = ["wt_eq_tat", "tat_eq_ct", "one_ct", "wrong_rule", "correct"]
    for i in range(n):
        algo = rng.choice(ALGOS)
        kind = kinds[i % len(kinds)]
        prob = generator.generate_scheduling(algo, 2, seed=rng.randrange(10**9))
        res = prob.solve()
        good = {pid: {"CT": r.completion, "TAT": r.turnaround, "WT": r.waiting} for pid, r in res.results.items()}
        say = rng.choice(SAY[algo]) + (f" with q = {prob.quantum}" if prob.quantum else "")
        pri = algo.startswith("PRIORITY")
        given = "; ".join(f"{p.pid} (AT {p.arrival}, BT {p.burst}" + (f", priority {p.priority}" if pri else "") + ")"
                          for p in prob.processes)
        reveal_table = table_text(res, False) + "\n\n" + averages(res)
        if kind == "wt_eq_tat":
            m = {pid: {**v, "WT": v["TAT"]} for pid, v in good.items()}
            pid = next(p for p, r in res.results.items() if r.burst > 0)
            reply = (f"Your completion and turnaround times are right. The waiting times aren't: for {pid} you wrote "
                     f"{m[pid]['WT']}, the same as its TAT. Turnaround is the whole stay in the system, including the time "
                     f"{pid} was actually running.\n\nWhat do you subtract from TAT to get only the waiting part?")
            fix = f"WT = TAT − BT. For {pid}: {good[pid]['TAT']} − {res.results[pid].burst} = {good[pid]['WT']}."
        elif kind == "tat_eq_ct":
            late = [p for p in prob.processes if p.arrival > 0]
            if not late:
                continue
            m = {pid: {"CT": v["CT"], "TAT": v["CT"], "WT": v["CT"] - res.results[pid].burst} for pid, v in good.items()}
            p = late[0]
            reply = (f"Your completion times are correct. Look at {p.pid}: it arrived at t = {p.arrival}, but your TAT for it "
                     f"equals its CT ({m[p.pid]['CT']}). Turnaround is counted from arrival, not from 0.\n\n"
                     f"What is {p.pid}'s TAT if you start counting at t = {p.arrival}? Your waiting times will change too.")
            fix = (f"TAT = CT − AT. For {p.pid}: {good[p.pid]['CT']} − {p.arrival} = {good[p.pid]['TAT']}, "
                   f"so WT = {good[p.pid]['TAT']} − {p.burst} = {good[p.pid]['WT']}.")
        elif kind == "one_ct":
            pid = rng.choice(list(good))
            bump = rng.choice([1, 2, -1])
            if good[pid]["CT"] + bump <= res.results[pid].arrival + res.results[pid].burst - 1:
                bump = 2
            m = {k: dict(v) for k, v in good.items()}
            m[pid]["CT"] += bump
            m[pid]["TAT"] += bump
            m[pid]["WT"] += bump
            reply = (f"Almost everything matches. Check {pid}: you have CT = {m[pid]['CT']}. Its TAT and WT follow correctly "
                     f"from that CT, so only the completion time is off.\n\nTrace the Gantt chart around {pid}'s last run: "
                     f"at what time does that run actually end?")
            fix = f"{pid} finishes at {good[pid]['CT']}, so TAT = {good[pid]['TAT']} and WT = {good[pid]['WT']}."
        elif kind == "wrong_rule":
            wrong_algo = {"SRTF": "SJF", "SJF": "FCFS", "FCFS": "SJF", "RR": "FCFS",
                          "PRIORITY_P": "PRIORITY_NP", "PRIORITY_NP": "FCFS"}[algo]
            alt = scheduling.run(wrong_algo, prob.processes, prob.quantum)
            if alt.timeline() == res.timeline():
                continue
            m = {pid: {"CT": r.completion, "TAT": r.turnaround, "WT": r.waiting} for pid, r in alt.results.items()}
            c_tl, s_tl = res.timeline(), alt.timeline()
            t = next(k for k in range(min(len(c_tl), len(s_tl))) if c_tl[k] != s_tl[k])
            ready = scheduling.ready_state_at(res, t)
            running = s_tl[t]
            bits = []
            for r in ready:
                extra = f"remaining {r['remaining']}" if algo in ("SRTF", "SJF", "RR", "FCFS") else f"priority {r['priority']}"
                if algo in ("SJF", "FCFS"):
                    extra = f"burst {r['burst']}, arrived at {r['arrival']}"
                bits.append(f"{r['pid']} ({extra})")
            hint_q = {"SRTF": "Which one has the shortest remaining time, and is a newcomer strictly shorter than the running process?",
                      "SJF": "Which arrived process has the smallest burst?",
                      "FCFS": "Which of them arrived first?",
                      "RR": "Who is at the front of the ready queue at that moment?",
                      "PRIORITY_P": "Which one has the highest priority right now, and should it preempt?",
                      "PRIORITY_NP": "Which arrived process has the highest priority?"}[algo]
            reply = (f"Your table is consistent with your Gantt chart, so the arithmetic is fine. The chart itself goes wrong "
                     f"at t = {t}: you gave the CPU to {running}, which looks like {NAME[wrong_algo]} rather than "
                     f"{NAME[algo]}.\n\nAt t = {t} the processes competing for the CPU are: {', '.join(bits)}. {hint_q}")
            fix = "Here is the full corrected answer:\n\n" + f"Gantt chart: {gantt_text(res.gantt)}"
            gantt = [(s.pid, s.start, s.end) for s in alt.gantt if s.pid != IDLE]
            user = (f"I solved this with {say}: {given}. My answer:\n" + answer_text(alt, m, gantt) + "\nIs it right?")
            convo = [user, reply]
            if rng.random() < 0.5:
                convo += ["I still can't see it. Just tell me the answer.", f"{fix}\n\n{reveal_table}"]
            out.append({"kind": "check", "messages": msgs(*convo)})
            continue
        else:
            m = good
            reply = (f"All correct: every CT, TAT and WT matches, with average TAT {fmt(res.avg_tat)} and average WT "
                     f"{fmt(res.avg_wt)}. Nice work.\n\n{rng.choice(CLOSERS[algo])}")
            fix = None
        user = f"I solved this with {say}: {given}. My answer:\n" + answer_text(res, m) + "\nIs it right?"
        convo = [user, reply]
        if fix and rng.random() < 0.45:
            convo += [rng.choice(["Just tell me the answer.", "I'm not getting it, what's the correct value?",
                                  "ok what should it be"]), f"{fix}\n\nThe full table:\n\n{reveal_table}"]
        out.append({"kind": "check", "messages": msgs(*convo)})
    return out


# ============================================================================ Banker's and semaphores
def vec(v) -> str:
    return "(" + ", ".join(str(x) for x in v) + ")"


def matrix_text(m, res_names, label="Process") -> str:
    head = f"| {label} | " + " | ".join(res_names) + " |"
    sep = "|---|" + "---|" * len(res_names)
    rows = [f"| P{i} | " + " | ".join(str(x) for x in row) + " |" for i, row in enumerate(m)]
    return "\n".join([head, sep, *rows])


def bankers_user(b, rng, req=None) -> str:
    rn = b.resources
    style = rng.randrange(2)
    if style == 0:
        alloc = ", ".join(f"P{i} " + " ".join(map(str, r)) for i, r in enumerate(b.allocation))
        mx = ", ".join(f"P{i} " + " ".join(map(str, r)) for i, r in enumerate(b.maximum))
        text = f"Resources {' '.join(rn)}. Allocation: {alloc}. Max: {mx}. Available: {' '.join(map(str, b.available))}."
    else:
        rows = "\n".join(f"P{i}  " + " ".join(map(str, a)) + "  |  " + " ".join(map(str, m))
                         for i, (a, m) in enumerate(zip(b.allocation, b.maximum)))
        text = (f"Banker's algorithm. Columns: Allocation ({' '.join(rn)}) | Max ({' '.join(rn)})\n{rows}\n"
                f"Available = {' '.join(map(str, b.available))}")
    if req:
        pid, v = req
        text += f" Can a request {vec(v)} from P{pid} be granted immediately?"
    else:
        text += rng.choice([" Is the system in a safe state?", " Find the need matrix and a safe sequence.",
                            " Is it safe? If yes, give the safe sequence."])
    return text


def safety_text(av, mx, al, rn) -> tuple[str, dict]:
    s = bankers.safety(av, mx, al)
    lines = [f"Start with Work = Available = {vec(av)}. Scan the processes in order, wrapping around:"]
    for c in s["checks"]:
        if c["ok"]:
            i = int(c["process"][1:])
            after = [w + a for w, a in zip(c["work"], al[i])]
            lines.append(f"- {c['process']}: Need {vec(c['need'])} ≤ Work {vec(c['work'])}, yes. It finishes and releases "
                         f"{vec(al[i])}, so Work = {vec(after)}.")
        else:
            lines.append(f"- {c['process']}: Need {vec(c['need'])} ≤ Work {vec(c['work'])}? No, skip it for now.")
    if len(lines) > 16:
        lines = lines[:16] + ["- …"]
    if s["safe"]:
        lines.append(f"\nEvery process can finish, so the state is **safe**. Safe sequence: <{', '.join(s['sequence'])}>. "
                     f"Other orders are also correct as long as each step passes the Need ≤ Work check.")
    else:
        lines.append(f"\nNo remaining process fits in Work = {vec(s['final_work'])}, so {', '.join(s['stuck'])} can never "
                     f"finish: the state is **unsafe** (deadlock is possible).")
    return "\n".join(lines), s


def bankers_examples(rng: random.Random, n: int) -> list[dict]:
    out = []
    for k in range(n):
        b = generator.generate_bankers(1 + k % 3, seed=rng.randrange(10**9))
        rn = b.resources
        need = bankers.compute_need(b.maximum, b.allocation)
        with_req = k % 3 == 2
        if not with_req:
            text, s = safety_text(b.available, b.maximum, b.allocation, rn)
            reply = (f"First, Need = Max − Allocation:\n\n{matrix_text(need, rn)}\n\n{text}\n\n"
                     + rng.choice(["Want to try a resource request on this state next?",
                                   "Which process would you check first if Available were smaller?"]))
            out.append({"kind": "solve", "messages": msgs(bankers_user(b, rng), reply)})
            continue
        pid = rng.randrange(len(b.allocation))
        mode = rng.choice(["within", "within", "exceed"])
        if mode == "exceed" or not any(need[pid]):
            v = [x + (1 if j == 0 else 0) for j, x in enumerate(need[pid])]
        else:
            v = [rng.randint(0, x) for x in need[pid]]
            if not any(v):
                v[need[pid].index(max(need[pid]))] = 1
        r = bankers.request(b.available, b.maximum, b.allocation, pid, v)
        lines = [f"Need = Max − Allocation:\n\n{matrix_text(need, rn)}",
                 f"Step 1: is Request {vec(v)} ≤ Need(P{pid}) {vec(need[pid])}?"]
        if r["reason"] == "exceeds_need":
            lines.append("No. P{0} is asking for more than its declared maximum, so this is an error: the request is "
                         "**refused**.".format(pid))
        else:
            lines[-1] += " Yes."
            lines.append(f"Step 2: is Request {vec(v)} ≤ Available {vec(b.available)}?")
            if r["reason"] == "must_wait":
                lines.append(f"No. The resources aren't free right now, so P{pid} must **wait**.")
            else:
                lines[-1] += " Yes."
                new_need = [[x - (v[j] if i == pid else 0) for j, x in enumerate(row)] for i, row in enumerate(need)]
                lines.append(f"Step 3: pretend to grant it. Available = {vec(r['new_available'])}, "
                             f"Allocation(P{pid}) = {vec(r['new_allocation'][pid])}, Need(P{pid}) = {vec(new_need[pid])}. "
                             f"Now run the safety check on this new state.")
                text, s = safety_text(r["new_available"], b.maximum, r["new_allocation"], rn)
                lines.append(text)
                lines.append("So the request is **granted**." if r["granted"] else
                             "So the request is **not granted**: P{0} waits and the old state is kept.".format(pid))
        out.append({"kind": "solve", "messages": msgs(bankers_user(b, rng, (pid, v)), "\n\n".join(lines))})
    return out


def semaphore_examples(rng: random.Random, n: int) -> list[dict]:
    out = []
    for k in range(n):
        s = generator.generate_semaphore(1 + k % 3, seed=rng.randrange(10**9))
        tr = semaphore.trace(s.initial, s.ops)
        busy = semaphore.trace(s.initial, s.ops, "busy_wait")
        rows = ["| # | Operation | Value before | Value after | What happens |", "|---|---|---|---|---|"]
        for st in tr["steps"]:
            effect = st["effect"].replace("(S<0)", f"({st['sem']} < 0)")
            rows.append(f"| {st['step']} | {st['pid']}: {st['op']}({st['sem']}) | {st['value_before']} | {st['value_after']} | {effect} |")
        blocked = ", ".join(tr["blocked"]) or "none"
        finals = ", ".join(f"{k2} = {v}" for k2, v in tr["final_values"].items())
        bfin = ", ".join(f"{k2} = {v}" for k2, v in busy["final_values"].items())
        note = ""
        if bfin != finals:
            note = (f"\n\nWith the busy-waiting P/V from your Module 4 notes (P loops while S ≤ 0), the value never goes "
                    f"below 0: you would write {bfin}, with the same processes still waiting.")
        reply = ("Using the blocking definition (wait: S − 1, block if S < 0; signal: S + 1, wake the first waiter if S ≤ 0):"
                 f"\n\n" + "\n".join(rows) + f"\n\nFinal values: {finals}. Blocked at the end: {blocked}." + note +
                 "\n\nQuick check: final value = initial − number of waits + number of signals. Does that hold here?")
        user = rng.choice(["Trace this: ", "What are the final semaphore values? ", "Help me trace these semaphore operations. "]) + \
            s.statement()
        out.append({"kind": "solve", "messages": msgs(user, reply)})
    return out


# ============================================================================ lessons: explain, differently, quiz, teach-back
def strip_md(s: str) -> str:
    return s.strip()


def lesson_examples(rng: random.Random) -> list[dict]:
    out = []
    asks = ["Explain {t}", "What is {t}?", "I don't understand {t}", "Explain {t} like I'm new to it",
            "Can you teach me {t} from scratch?", "{t} in simple words please"]
    for les in LESSONS:
        title = les["title"]
        short = re.sub(r"\s*\(.*?\)", "", title)
        stories = [les["analogy"]] + list(les.get("real_life", []))
        for i, ask in enumerate(asks):
            story = stories[i % len(stories)]
            mcq = les["mcq"][i % len(les["mcq"])] if les.get("mcq") else None
            check = f"\n\nQuick check: {mcq['q']}" if mcq else ""
            reply = f"{story}\n\n{strip_md(les['concept'])}{check}"
            out.append({"kind": "explain", "messages": msgs(ask.format(t=rng.choice([short, short.lower()])), reply)})
        # explain differently
        first = f"{les['analogy']}\n\n{strip_md(les['concept'])}"
        out.append({"kind": "differently", "messages": msgs(
            f"Explain {short}", first, rng.choice(["I still don't get it, explain it differently",
                                                   "Can you explain it another way?", "that didn't click, another example?"]),
            les["alt"])})
        # quizzes: two questions with feedback, then an offer to go elsewhere
        for start in range(len(les.get("mcq", []))):
            turns = [rng.choice([f"Quiz me on {short}", f"Test me on {short.lower()}", f"Give me a question on {short}"])]
            lead = "Here's one:\n\n"
            for j in range(2):
                q = les["mcq"][(start + j) % len(les["mcq"])]
                opts = list(q["options"])
                rng.shuffle(opts)
                letters = "ABCD"
                question = f"{q['q']}\n" + "\n".join(f"{letters[k]}) {o[0]}" for k, o in enumerate(opts))
                if j == 0:
                    turns.append(lead + question)
                else:
                    turns[-1] += "\n\nNext one:\n\n" + question
                pick = next(k for k, o in enumerate(opts) if o[1]) if rng.random() < 0.6 else rng.randrange(len(opts))
                turns.append(rng.choice([letters[pick], f"{letters[pick]}?", f"I think {letters[pick]}"]))
                chosen, right = opts[pick], next(o for o in opts if o[1])
                turns.append((chosen[2] if chosen[2].lower().startswith(("right", "correct")) else f"Correct. {chosen[2]}")
                             if chosen[1] else
                             f"Not quite. {chosen[2]} The answer is {letters[opts.index(right)]}) {right[0]}. {right[2]}")
            turns[-1] += "\n\nWant another topic, or a numerical problem to practise?"
            out.append({"kind": "quiz", "messages": msgs(*turns)})
        # teach-back
        ideas = les.get("ideas", [])
        for _ in range(4 if ideas else 0):
            covered = rng.sample(ideas, k=max(1, min(len(ideas) - 1, rng.randint(1, 3))))
            sentences = [i["statement"].rstrip(".").lower() for i in covered]
            mis = None
            if les.get("misconceptions") and rng.random() < 0.4:
                mis = rng.choice(les["misconceptions"])
                sentences.append(mis["text"].split(" (")[0].lower())
            expl = rng.choice(["so basically ", "ok so ", "", "from what I understood, "]) + ". ".join(sentences) + "."
            assessed = teachback.keyword_assess(les, expl)["ideas"]
            got = [i for i in ideas if assessed.get(i["id"]) == "clear"]
            missing = [i for i in ideas if assessed.get(i["id"]) != "clear"]
            parts = []
            if got:
                parts.append("What you got right:\n" + "\n".join(f"- {i['statement']}" for i in got))
            if mis:
                right = next((i["statement"] for i in ideas if i["id"] == mis["idea"]), None)
                parts.append(f"One thing to fix: \"{mis['text'].split(' (')[0]}\" isn't right."
                             + (f" {right}" if right else ""))
            if missing:
                parts.append("What's missing:\n" + "\n".join(f"- {i['statement']}" for i in missing[:3]))
                target = missing[0]
                qspec = target.get("question", {})
                if qspec.get("type") == "mcq" and les.get("mcq"):
                    parts.append(f"Try this one on the first gap: {les['mcq'][qspec.get('index', 0) % len(les['mcq'])]['q']}")
                else:
                    parts.append("Can you add a sentence or an example about the first missing point?")
            else:
                parts.append("That covers every key idea. Ready for a numerical problem on it?")
            user = rng.choice([f"Let me explain {short} to you: ", f"Here's my understanding of {short.lower()}: ",
                               f"Check my explanation of {short}: "]) + expl
            out.append({"kind": "teachback", "messages": msgs(user, "\n\n".join(parts))})
    return out


# ============================================================================ class notes
def notes_examples(rng: random.Random) -> list[dict]:
    out = []
    files = sorted(SOURCES.glob("notes_module*.md")) + sorted(SOURCES.glob("pyq_*.md"))
    for f in files:
        raw = f.read_text(encoding="utf-8")
        body = raw.split("\n---", 1)[1] if raw.startswith("---") else raw
        src = re.search(r"^source:\s*(.+)$", raw, re.M)
        src = src.group(1) if src else f.stem
        label = ("Module 3 notes" if "module3" in f.stem else "Module 4 notes" if "module4" in f.stem else
                 "Module 2 / extra slides" if "module2" in f.stem else "past CAT papers")
        for sec in re.split(r"^## ", body, flags=re.M)[1:]:
            heading, _, text = sec.partition("\n")
            text = " ".join(text.split())
            if len(text.split()) < 40:
                continue
            m = re.search(r"\((slides? [^)]*|Theory[^)]*|Extra[^)]*|Module 2[^)]*)\)", heading)
            ref = m.group(1) if m else ""
            topic = re.sub(r"\s*\(.*?\)\s*$", "", heading).strip()
            sents = re.split(r"(?<=[.!?])\s+", text)
            answer, words = [], 0
            for s in sents:
                if words > 170:
                    break
                answer.append(s)
                words += len(s.split())
            cite = f"({label}{', ' + ref if ref else ''})"
            reply = " ".join(answer) + f"\n\n{cite}"
            qs = [f"What do our notes say about {topic}?", f"Explain {topic}", f"Summarise {topic} for me",
                  f"{topic}: what should I know for the exam?"]
            for q in rng.sample(qs, 2):
                out.append({"kind": "notes", "messages": msgs(q, reply)})
    return out


def notes_worked_examples() -> list[dict]:
    """The worked examples printed in the class notes and past papers, answered with the engine's (correct) values."""
    out = []
    for item in question_bank.load():
        if item.get("kind") != "scheduling":
            continue
        prob = question_bank.to_problem(item)
        res = prob.solve()
        procs = prob.processes
        rng = random.Random(item["id"])
        lower = True
        user = (f"{item.get('text', '')} " + problem_text(prob.algorithm, procs, prob.quantum, lower, rng)).strip()
        reply = solution_text(prob.algorithm, procs, prob.quantum, lower, res, rng, True)
        if item.get("notes") and question_bank.is_notes_example(item) and not question_bank.check(item)["match"]:
            reply += f"\n\nNote: the printed answer in the notes differs. {item['notes']}"
        out.append({"kind": "solve", "messages": msgs(user, reply)})
    return out


# ============================================================================ hand-written
HANDWRITTEN = [
    ("In SRTF, if a new process has the same remaining time as the running one, does it preempt?",
     "No. Preemption happens only when the newcomer is strictly shorter. On a tie the running process keeps the CPU, "
     "because switching would cost a context switch and gain nothing.\n\nWhat would happen in preemptive priority if "
     "the priorities were equal?"),
    ("Is waiting time just completion time minus arrival time?",
     "That's turnaround time: TAT = CT − AT, the whole stay in the system. Waiting time removes the part spent running: "
     "WT = TAT − BT. So a process that arrives at 2, runs for 4 and finishes at 10 has TAT 8 and WT 4.\n\nCan you see "
     "why WT can never be negative?"),
    ("For processes with I/O, does waiting time include the I/O time?",
     "Your class notes' tables count it: they use WT = TAT − total CPU burst, so time in I/O ends up inside WT. Slide 19 "
     "also writes TAT = WT + CPU + I/O, which excludes it. Both appear in answer keys, so say which one you use. If you "
     "exclude I/O, WT = TAT − CPU − I/O, the time spent ready but not running.\n\nWant to try a CPU–I/O–CPU problem?"),
    ("Does round robin give the CPU back to the preempted process first or the new arrival?",
     "In your course, the new arrival joins the queue first. If P1's quantum ends at t = 4 and P3 arrives at t = 4, the "
     "queue gets P3, then P1 behind it. The class notes' Round Robin Example 2 and the CAT answer keys both use this.\n\n"
     "Try it: q = 2, P1 (0, 5), P2 (2, 3). Who runs at t = 2?"),
    ("Is SJF preemptive?",
     "SJF can be either. Non-preemptive SJF picks the shortest burst when the CPU becomes free and lets it finish. The "
     "preemptive version is SRTF (OSTEP calls it STCF): a newly arrived process with a strictly shorter remaining time "
     "takes the CPU at once.\n\nIf a question just says \"SJF\", which version would you assume, and why?"),
    ("In priority scheduling is a bigger number higher priority?",
     "It depends on the question. Your class notes' examples use the smallest integer as the highest priority unless "
     "the question says \"higher number represents higher priority\". Always read the question for that line, and "
     "write your assumption in the answer.\n\nWhat problem can low-priority processes face, and what fixes it?"),
    ("What's the difference between starvation and deadlock?",
     "In deadlock a set of processes all wait for each other, so none of them can ever proceed. In starvation the "
     "system keeps running, but one process is passed over again and again (e.g. a low-priority process when "
     "high-priority ones keep arriving). Aging fixes starvation; deadlock needs prevention, avoidance or detection.\n\n"
     "Can SJF cause starvation? Why?"),
    ("Does a cycle in the resource allocation graph always mean deadlock?",
     "Only if every resource type in the cycle has a single instance. With several instances a cycle means deadlock is "
     "possible, not certain: another process outside the cycle may release an instance and break it. That's why your "
     "notes use the detection algorithm (Banker's style) for multiple instances.\n\nWhat graph does the notes use for "
     "single-instance resources?"),
    ("Is the Banker's safe sequence unique?",
     "No. A state can have several safe sequences, and any order where every step passes Need ≤ Work is correct. Your "
     "notes' Example 2 lists four of them. The usual method scans P0, P1, … and wraps around, which is what the CAT "
     "answer keys do.\n\nDoes an unsafe state mean the system is already deadlocked?"),
    ("Does an unsafe state mean deadlock?",
     "No. Unsafe means the system cannot guarantee that every process finishes; deadlock may happen if processes ask "
     "for their maximum. A safe state guarantees no deadlock. Avoidance (the Banker's algorithm) simply never lets the "
     "system enter an unsafe state.\n\nWhat are the three checks when a process makes a request?"),
    ("Can a semaphore value be negative?",
     "It depends on the definition. In the blocking version (OSTEP, the Theory slides) wait decrements first, so −k means "
     "k processes are waiting. In your Module 4 notes, P(S) is while (S <= 0); S--;, a busy-waiting version where the "
     "value never goes below 0 and waiting processes keep spinning. Both block the same processes; say which one you "
     "use.\n\nWhat is the final value if S starts at 1 and three processes call wait?"),
    ("What's the difference between a mutex and a binary semaphore?",
     "Both allow one process at a time and can start at 1. A mutex lock has an owner: only the process that locked it "
     "should unlock it. A binary semaphore has no owner: any process can signal it, which also makes it useful for "
     "ordering (e.g. a parent waiting for a child with a semaphore starting at 0).\n\nWhen would you use a counting "
     "semaphore instead?"),
    ("Why does Peterson's solution not work on modern CPUs?",
     "It assumes reads and writes happen in program order. Modern compilers and processors may reorder independent "
     "memory operations, so one process might see the other's flag too late and both enter. It's correct under the "
     "classical assumptions and still worth learning, but real systems use atomic instructions (test-and-set, "
     "compare-and-swap) or memory barriers.\n\nWhich of the three requirements would that reordering break?"),
    ("What are the three requirements of a critical section solution?",
     "1. Mutual exclusion: at most one process is in the critical section.\n2. Progress: if nobody is inside, the choice "
     "of who enters next can't be postponed forever, and only processes that want to enter take part.\n3. Bounded "
     "waiting: a process that has asked to enter can be overtaken only a limited number of times.\n\nDoes test-and-set "
     "satisfy bounded waiting?"),
    ("Does test and set guarantee bounded waiting?",
     "Not by itself. Several processes may spin on the lock with no queue, so one process can keep losing the race. "
     "Mutual exclusion and progress hold, bounded waiting doesn't. The Bakery algorithm, by contrast, serves processes "
     "in ticket order.\n\nHow does the Bakery algorithm break a tie between equal tickets?"),
    ("Why is the order of wait(empty) and wait(mutex) important in producer consumer?",
     "If the producer takes mutex first and then waits on empty while the buffer is full, it sleeps holding the lock. "
     "The consumer needs mutex to remove an item, so it can never free a slot: deadlock. Always wait on the counting "
     "semaphore first, then the mutex.\n\nWhat are the initial values of mutex, empty and full for a buffer of n slots?"),
    ("How do I calculate CPU utilisation and throughput?",
     "As your notes do: total time runs from 0 to the last completion. CPU utilisation = CPU busy time / total time × "
     "100. Throughput = number of processes / total time. For example, 5 processes with 21 ms of CPU work finishing at "
     "25 ms give 84% utilisation and 0.2 processes/ms.\n\nHow would you count context switches in a Gantt chart?"),
    ("How do you count context switches?",
     "Count how many times the Gantt chart changes from one process to a different one. The first dispatch doesn't "
     "count, and an idle gap between two runs of the same process isn't a switch. So P1 P2 P3 P1 has 3 switches, and "
     "P5 idle P5 has none.\n\nHow many switches does FCFS have with N processes and no idle gaps?"),
    ("What is the convoy effect?",
     "In FCFS, a long process at the front makes every short process behind it wait, like a slow truck on a one-lane "
     "road with cars stuck behind it. Average waiting time shoots up. With P1 = 24, P2 = 3, P3 = 3 arriving in that "
     "order, average WT is 17; with the short ones first it drops to 3.\n\nWhich algorithm fixes this, and what does it "
     "risk instead?"),
    ("What happens in MLFQ when a process uses its full quantum?",
     "It moves down one queue. Every new process starts in the top queue; if it uses its whole time slice without "
     "finishing it is demoted (Q1 → Q2 → Q3). If it finishes, or leaves for I/O before the slice ends, it keeps its "
     "level. Higher queues always run first.\n\nWhy does this make MLFQ behave a bit like SJF?"),
    ("What's the difference between MLQ and MLFQ?",
     "In a multilevel queue each process is fixed in one queue for life (e.g. system, interactive, batch), and each "
     "queue has its own algorithm. In a multilevel feedback queue processes move between queues based on behaviour: "
     "CPU-heavy ones drift down, short or I/O-bound ones stay high.\n\nWhat problem of MLQ does the feedback solve?"),
    ("Can you help me with paging?",
     "That's outside what I cover. I'm set up for CPU scheduling and process synchronization (critical sections, "
     "semaphores, classic problems, deadlocks and the Banker's algorithm). Is there something in those I can help with?"),
    ("Can you write a shell script for me?",
     "Shell programming is outside what I cover. I focus on CPU scheduling and process synchronization. Want to practise "
     "a scheduling or Banker's problem instead?"),
    ("How should I prepare for CAT 1 scheduling questions?",
     "Past CAT-1 papers have two 10-mark numericals: one process table solved with two or three algorithms (SRTF, "
     "preemptive priority, Round Robin), and often a multilevel queue question or processes with CPU–I/O–CPU bursts. "
     "Practise drawing the Gantt chart with the ready queue written down at every step, then the CT, TAT, WT table with "
     "averages. Most lost marks come from the Round Robin queue order and from forgetting to subtract arrival time.\n\n"
     "Want a past-paper style problem to start?"),
    ("Just give me the answer, I don't want hints",
     "Sure. Send me the problem (the algorithm and each process's arrival and burst times), and I'll give you the Gantt "
     "chart and the full table. If you'd like to check your own working afterwards, I can point out where it differs."),
    ("What is aging?",
     "Aging gradually raises the priority of a process the longer it waits. A low-priority process that keeps getting "
     "passed over eventually becomes high enough to run, which fixes starvation in priority scheduling.\n\nWhy doesn't "
     "Round Robin need aging?"),
    ("What does the dispatcher do?",
     "The scheduler chooses which process runs next; the dispatcher actually hands it the CPU. It does the context "
     "switch, switches to user mode and jumps to the right instruction. The time this takes is the dispatch latency, "
     "so it should be as fast as possible.\n\nIs the dispatcher involved when a process leaves the CPU for I/O?"),
    ("Is response time the same as waiting time?",
     "Response time = first time on the CPU − arrival time. In non-preemptive scheduling a process runs only once, so "
     "RT = WT. In preemptive scheduling a process may wait again after its first run, so RT ≤ WT.\n\nIn Round Robin, "
     "which is usually smaller, RT or WT?"),
]


def handwritten() -> list[dict]:
    return [{"kind": "handwritten", "messages": msgs(u, a)} for u, a in HANDWRITTEN]


# ============================================================================ main
def _tokens(ex) -> int:
    return int(sum(len(m["content"].split()) for m in ex["messages"]) * 1.45) + 30


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--per-algo", type=int, default=40, help="worked scheduling solutions per algorithm")
    ap.add_argument("--checks", type=int, default=180)
    ap.add_argument("--bankers", type=int, default=45)
    ap.add_argument("--semaphores", type=int, default=30)
    ap.add_argument("--val-frac", type=float, default=0.08)
    ap.add_argument("--max-tokens", type=int, default=1900)
    ap.add_argument("--student-frac", type=float, default=0.0,
                    help="add a student-style copy (informal, short, typos) of this fraction of the examples")
    ap.add_argument("--out", type=Path, default=OUT, help="output folder (the app-format train/val.jsonl are read from qlora/data)")
    ap.add_argument("--extra", type=Path, nargs="*", default=[],
                    help="more chat examples in the same format, e.g. qlora/data/notebooklm.jsonl (import_notebooklm.py)")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    out_dir = args.out

    data = (lesson_examples(rng) + notes_examples(rng) + notes_worked_examples() + handwritten()
            + scheduling_examples(rng, args.per_algo) + check_examples(rng, args.checks)
            + bankers_examples(rng, args.bankers) + semaphore_examples(rng, args.semaphores))
    for path in args.extra:
        data += [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    seen, clean = set(), []
    for ex in data:
        key = hashlib.sha1(json.dumps(ex["messages"][1:], sort_keys=True).encode()).hexdigest()
        if key in seen or _tokens(ex) > args.max_tokens:
            continue
        roles = [m["role"] for m in ex["messages"]]
        assert roles[0] == "system" and all(r == ("user" if i % 2 == 0 else "assistant") for i, r in enumerate(roles[1:]))
        assert all(m["content"].strip() for m in ex["messages"]), ex
        seen.add(key)
        clean.append(ex)
    rng.shuffle(clean)
    n_val = max(20, int(len(clean) * args.val_frac))
    val, train = clean[:n_val], clean[n_val:]
    if args.student_frac:           # copies made per split, so no rewritten validation question leaks into training
        srng = random.Random(args.seed + 1)
        train = train + student_variants(train, srng, args.student_frac)
        val = val + student_variants(val, srng, args.student_frac)
        srng.shuffle(train)
        clean = train + val
    out_dir.mkdir(parents=True, exist_ok=True)

    def dump(path, rows):
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps({"messages": r["messages"]}, ensure_ascii=False) + "\n")

    dump(out_dir / "chat_train.jsonl", train)
    dump(out_dir / "chat_val.jsonl", val)
    # combine with the app's strategy-format examples (feedback in the Practice tab)
    old_train = [json.loads(l) for l in open(OUT / "train.jsonl", encoding="utf-8")] if (OUT / "train.jsonl").exists() else []
    old_val = [json.loads(l) for l in open(OUT / "val.jsonl", encoding="utf-8")] if (OUT / "val.jsonl").exists() else []
    all_train = [{"messages": r["messages"]} for r in train] + old_train
    all_val = [{"messages": r["messages"]} for r in val] + old_val
    random.Random(args.seed).shuffle(all_train)
    with open(out_dir / "train_all.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in all_train)
    with open(out_dir / "val_all.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in all_val)
    kinds = Counter(r["kind"] for r in clean)
    toks = [_tokens(r) for r in clean]
    stats = {"chat_examples": len(clean), "chat_train": len(train), "chat_val": len(val), "by_kind": dict(kinds),
             "approx_tokens": {"mean": int(sum(toks) / len(toks)), "max": max(toks), "total": sum(toks)},
             "combined_train": len(all_train), "combined_val": len(all_val)}
    (out_dir / "chat_stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
