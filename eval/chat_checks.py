"""
Measurements of the chat tutor that need no GPU (the language model is switched off):

  1. Routing: 70 student messages, written in everyday phrasing, each with the action a teacher would expect.
     Only the rules and the keyword fallback run (the LLM router is off), so this is the floor.
  2. Reading pasted problems: 120 engine-generated problems, each written in 6 common layouts.
  3. Reading typed answers: the engine's correct answer to each problem in 4 formats, sent through the whole
     chat agent; it must be marked correct. Then one mistake (WT = TAT for one process) must be found.
  4. The answer-leak guard: hint replies that state the hidden correct value must be blocked, hints that
     don't must pass. Run with the old and the fixed number matcher.

    python -m eval.chat_checks          → prints a table and writes eval/results_chat_checks.md
"""
from __future__ import annotations

import random
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace

from engine import generator, scheduling
from engine.generator import SchedulingProblem
from engine.scheduling import IDLE
from rag.store import KnowledgeBase
from tutor import chat_parse as cp
from tutor import prompts
from tutor.chat_agent import ChatAgent, new_state
from tutor.student_model import StudentModel

OUT = Path(__file__).resolve().parent
OLD_NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")     # the matcher before the fix

BANKERS_TEXT = ("Allocation:\nP0 0 1 0\nP1 2 0 0\nP2 3 0 2\nP3 2 1 1\nP4 0 0 2\nMax:\nP0 7 5 3\nP1 3 2 2\nP2 9 0 2\n"
                "P3 2 2 2\nP4 4 3 3\nAvailable: 3 3 2. Is the system in a safe state?")

# (message, state, acceptable actions). States: S0 nothing open · S0t topic "rr" · S1 open Round Robin problem ·
# S2 open Banker's problem · S3 quiz running · S4 waiting for a teach-back explanation
ROUTING = [
    ("explain round robin", "S0", {"explain"}),
    ("can you teach me SRTF from scratch", "S0", {"explain"}),
    ("i dont understand semaphores", "S0", {"explain"}),
    ("what is a deadlock", "S0", {"explain"}),
    ("explain FCFS like I'm 5", "S0", {"explain"}),
    ("teach me the bankers algorithm", "S0", {"explain"}),
    ("how does priority scheduling work", "S0", {"explain"}),
    ("what is the critical section problem", "S0", {"explain"}),
    ("tell me about sjf", "S0", {"explain"}),
    ("go over turnaround and waiting time again", "S0", {"explain"}),
    ("can you break down how the ready queue works in RR?", "S0", {"explain", "ask"}),
    ("explain it differently", "S0t", {"explain"}),
    ("still don't get it, simpler please", "S0t", {"explain"}),
    ("what's the difference between SJF and SRTF?", "S0", {"ask", "faq"}),
    ("why does round robin have more context switches?", "S0", {"ask"}),
    ("what is peterson's solution?", "S0", {"ask", "faq"}),
    ("what is the convoy effect?", "S0", {"ask", "faq"}),
    ("can a safe state become unsafe?", "S0", {"ask"}),
    ("which algorithm gives the minimum average waiting time?", "S0", {"ask"}),
    ("what do my notes say about the bakery algorithm?", "S0", {"ask"}),
    ("is starvation possible in SJF?", "S0", {"ask", "faq"}),
    ("when should I use a binary semaphore instead of a mutex?", "S0", {"ask"}),
    ("what happens if signal is called before wait?", "S0", {"ask"}),
    ("give me a problem", "S0", {"practice"}),
    ("give me a hard round robin question", "S0", {"practice"}),
    ("I want to practice SRTF", "S0", {"practice"}),
    ("test me on priority scheduling", "S0", {"practice"}),
    ("give me a past paper question", "S0", {"practice"}),
    ("give me an easy banker's problem", "S0", {"practice"}),
    ("give me a numerical on fcfs", "S0", {"practice"}),
    ("practise semaphores", "S0", {"practice"}),
    ("another one", "S1", {"practice"}),
    ("something harder", "S1", {"practice"}),
    ("quiz me on deadlocks", "S0", {"quiz"}),
    ("can you give me some MCQs on SJF", "S0", {"quiz"}),
    ("quiz me", "S0", {"quiz"}),
    ("b", "S3", {"quiz_answer"}),
    ("option c", "S3", {"quiz_answer"}),
    ("stop the quiz", "S3", {"quiz_stop"}),
    ("let me explain round robin", "S0", {"teachback"}),
    ("can I explain SRTF back to you", "S0", {"teachback"}),
    ("Round robin gives every process a fixed time quantum and moves unfinished ones to the back of the queue",
     "S4", {"teachback_assess"}),
    ("how am I doing?", "S0", {"progress"}),
    ("what should I practice next?", "S0", {"progress"}),
    ("show my progress", "S0", {"progress"}),
    ("where am I weak", "S0", {"progress"}),
    ("hint please", "S1", {"hint"}),
    ("I'm stuck", "S1", {"hint"}),
    ("how do I start?", "S1", {"hint"}),
    ("show me the solution", "S1", {"reveal"}),
    ("I give up, just tell me the answer", "S1", {"reveal"}),
    ("solve it for me", "S1", {"reveal"}),
    ("I'll try it first", "S1", {"try_first"}),
    ("P1 0-2, P2 2-4, P3 4-6", "S1", {"check"}),
    ("P1: CT 9, TAT 9, WT 4", "S1", {"check"}),
    ("CT: 9, 7, 10\nTAT: 9, 6, 8\nWT: 4, 3, 6", "S1", {"check"}),
    ("| P1 | P2 | P3 |\n0 2 4 6", "S1", {"check"}),
    ("average waiting time = 4.33", "S1", {"check"}),
    ("safe: P1, P3, P4, P0, P2", "S2", {"check"}),
    ("unsafe", "S2", {"check"}),
    ("what does safe state mean?", "S2", {"ask"}),
    ("now solve it with SJF", "S1", {"solve"}),
    ("Solve using SRTF: P1 AT=0 BT=8, P2 AT=1 BT=4, P3 AT=2 BT=9", "S0", {"solve"}),
    ("Round robin q=2: P1(0,5), P2(1,3), P3(2,1)", "S0", {"offer"}),
    ("Process Arrival Burst\nP1 0 5\nP2 1 3\nP3 2 8", "S0", {"need_algorithm"}),
    ("FCFS: P1 AT=0 BT=5, P2 AT=1 BT=3. My answer: P1 0-5, P2 5-8", "S0", {"pasted_check"}),
    (BANKERS_TEXT, "S0", {"offer", "solve"}),
    ("hi", "S0", {"chat"}),
    ("thanks!", "S0", {"chat"}),
    ("what's the capital of france", "S0", {"chat"}),
]

ALGO_WORDS = {"FCFS": "FCFS", "SJF": "non-preemptive SJF", "SRTF": "SRTF", "RR": "Round Robin with time quantum {q}",
              "PRIORITY_NP": "non-preemptive priority", "PRIORITY_P": "preemptive priority"}


def _agent(tmp: Path, kb) -> ChatAgent:
    a = ChatAgent(StudentModel(tmp / "checks.db"), kb, None, use_llm=False)
    a.raise_errors = True
    return a


def _state(kind: str, agent: ChatAgent) -> dict:
    st = new_state("checks")
    if kind == "S0t":
        st["topic"] = "rr"
    if kind == "S1":                                  # Round Robin, q = 2: P1(0,5), P2(1,3), P3(2,1)
        agent._new_problem_state(st, SchedulingProblem("RR", 1, [scheduling.Process("P1", 0, 5), scheduling.Process("P2", 1, 3),
                                                                 scheduling.Process("P3", 2, 1)], quantum=2))
    if kind == "S2":
        agent._new_problem_state(st, generator.generate_bankers(1, seed=7))
    if kind == "S3":
        r = agent.respond(st, "quiz me on deadlocks")
        agent.commit(st, r)
    if kind == "S4":
        r = agent.respond(st, "let me explain round robin")
        agent.commit(st, r)
    return st


def check_routing(agent: ChatAgent) -> tuple[int, int, list[str]]:
    ok, misses = 0, []
    for msg, kind, want in ROUTING:
        route = agent.route(_state(kind, agent), msg)
        if route.action in want:
            ok += 1
        else:
            misses.append(f"{msg[:60]!r}: got {route.action}, expected {'/'.join(sorted(want))}")
    return ok, len(ROUTING), misses


def layouts(p: SchedulingProblem) -> list[str]:
    pri = p.algorithm.startswith("PRIORITY")
    name = ALGO_WORDS[p.algorithm].format(q=p.quantum)
    ps = p.processes
    pr = lambda x: f" priority={x.priority}" if pri else ""          # noqa: E731
    return [
        f"Solve using {name}: " + ", ".join(f"{x.pid} AT={x.arrival} BT={x.burst}{pr(x)}" for x in ps),
        f"{name}: " + ", ".join(f"{x.pid}({x.arrival},{x.burst}" + (f",{x.priority}" if pri else "") + ")" for x in ps)
        + (". Third value is the priority." if pri else ""),
        "Process Arrival Burst" + (" Priority" if pri else "") + "\n"
        + "\n".join(f"{x.pid} {x.arrival} {x.burst}" + (f" {x.priority}" if pri else "") for x in ps) + f"\nUse {name}.",
        "| Process | AT | BT |" + (" Priority |" if pri else "") + "\n|---|---|---|" + ("---|" if pri else "") + "\n"
        + "\n".join(f"| {x.pid} | {x.arrival} | {x.burst} |" + (f" {x.priority} |" if pri else "") for x in ps)
        + f"\nSchedule with {name}.",
        f"Arrival times: {', '.join(str(x.arrival) for x in ps)}. Burst times: {', '.join(str(x.burst) for x in ps)}."
        + (f" Priorities: {', '.join(str(x.priority) for x in ps)}." if pri else "") + f" Use {name}.",
        "; ".join(f"{x.pid} arrives at {x.arrival} and needs {x.burst} units" + (f" with priority {x.priority}" if pri else "")
                  for x in ps) + f". Schedule them with {name}.",
    ]


def check_problem_parsing(problems: list[SchedulingProblem]) -> tuple[int, int, list[str]]:
    ok = total = 0
    misses = []
    for p in problems:
        want = [(x.pid, x.arrival, x.burst, x.priority if p.algorithm.startswith("PRIORITY") else 0) for x in p.processes]
        for k, text in enumerate(layouts(p)):
            total += 1
            got = cp.parse_scheduling_problem(text)
            good = (got is not None and [(x.pid, x.arrival, x.burst, x.priority) for x in got["processes"]] == want
                    and got["algorithms"][:1] == [p.algorithm]
                    and (p.algorithm != "RR" or got["quantum"] == p.quantum))
            ok += good
            if not good and len(misses) < 8:
                misses.append(f"layout {k + 1}: {text[:70]!r}")
    return ok, total, misses


def answer_texts(p: SchedulingProblem, wrong_pid: str | None = None) -> list[str]:
    res = p.solve()
    segs = [(s.pid, s.start, s.end) for s in res.gantt]
    rows = []
    for x in p.processes:
        r = res.results[x.pid]
        rows.append((x.pid, r.completion, r.turnaround, r.turnaround if x.pid == wrong_pid else r.waiting))
    name = lambda pid: "idle" if pid == IDLE else pid                  # noqa: E731
    g1 = ", ".join(f"{name(a)} {s}-{e}" for a, s, e in segs)
    g2 = "| " + " | ".join(name(a) for a, _, _ in segs) + " |\n" + " ".join(str(t) for t in [segs[0][1]] + [e for _, _, e in segs])
    g3 = ", ".join(f"{s}-{e} {name(a)}" for a, s, e in segs)
    g4 = " ".join(f"{name(a)}({s}-{e})" for a, s, e in segs)
    m1 = "; ".join(f"{pid}: CT {ct}, TAT {tat}, WT {wt}" for pid, ct, tat, wt in rows)
    m2 = "Process CT TAT WT\n" + "\n".join(f"{pid} {ct} {tat} {wt}" for pid, ct, tat, wt in rows)
    m3 = "\n".join(f"{lab}: " + ", ".join(str(r[i]) for r in rows) for i, lab in ((1, "CT"), (2, "TAT"), (3, "WT")))
    m4 = ", ".join(f"{pid} completion time {ct} turnaround {tat} waiting {wt}" for pid, ct, tat, wt in rows)
    return [f"{g1}\n{m1}", f"{g2}\n{m2}", f"{g3}\n{m3}", f"{g4}\n{m4}"]


def check_answers(agent: ChatAgent, problems: list[SchedulingProblem]) -> dict:
    out = {"right_ok": 0, "right_n": 0, "wrong_ok": 0, "wrong_n": 0, "misses": []}
    for p in problems:
        wrong_pid = next((x.pid for x in p.processes if x.burst > 0 and p.solve().results[x.pid].waiting >= 0), None)
        for k, text in enumerate(answer_texts(p)):
            st = new_state("checks")
            agent._new_problem_state(st, p)
            r = agent.respond(st, text)
            out["right_n"] += 1
            good = r.meta.get("action") == "check" and st["problem"]["solved"]
            out["right_ok"] += good
            if not good and len(out["misses"]) < 6:
                out["misses"].append(f"format {k + 1} ({p.algorithm}): routed {r.meta.get('action')}")
        for text in answer_texts(p, wrong_pid)[:2]:
            st = new_state("checks")
            agent._new_problem_state(st, p)
            agent.respond(st, text)
            a = st["problem"].get("analysis") or {}
            out["wrong_n"] += 1
            out["wrong_ok"] += any(e["type"] == "wt_forgot_burst" for e in a.get("errors", []))
    return out


LEAKS = ["Your {pid} waiting time should be {n}.", "The correct WT for {pid} is {n}", "So {pid} waits {n} units in total.",
         "It should come out to {n}.", "WT = {n} for {pid}, not what you wrote."]
SAFE = ["Look at your waiting time for {pid} again. What do you subtract from the turnaround time?",
        "Your chart is right. Check the formula you used for {pid}: is the burst time included?"]
# when the hidden value is also a number in the problem data, a safe hint may quote that number as data
SAFE_DATA = ["Your waiting time for {pid} needs the burst time; one of the bursts in the table is {n}.",
             "Check the arrival and burst values again (look at the {n} in the table) before you subtract."]


def check_guard(agent: ChatAgent, problems: list[SchedulingProblem]) -> dict:
    from tutor import strategy as sm
    stats = {"leaks": 0, "caught_old": 0, "caught_new": 0, "safe": 0, "false_old": 0, "false_new": 0, "excluded": 0,
             "amb_leaks": 0, "amb_caught": 0, "amb_safe": 0, "amb_false": 0}
    for p in problems:
        res = p.solve()
        x = max(p.processes, key=lambda q: res.results[q.pid].waiting)
        if res.results[x.pid].waiting == 0:
            continue
        text = answer_texts(p, x.pid)[0]
        st = new_state("checks")
        agent._new_problem_state(st, p)
        agent.respond(st, text)
        a = st["problem"]["analysis"]
        strat = sm.decide(p, a, "beginner", [], 1, 0)
        if strat.reveal or not strat.secrets.get("numbers"):
            continue
        n = strat.secrets["numbers"][0]
        wt = next((v["value"] for v in strat.secrets.get("values", []) if v["pid"] == x.pid and v["field"] == "WT"), None)
        fact_nums = {m.group(0) for m in prompts.NUM.finditer(" ".join(strat.facts))}
        if wt is not None and str(wt) in fact_nums:
            # the hidden WT is also a number in the problem data: judged by context ("waiting time … 4")
            stats["excluded"] += 1
            for t in LEAKS:
                stats["amb_leaks"] += 1
                stats["amb_caught"] += any(i["type"] == "revealed_answer"
                                           for i in prompts.check_response(t.format(pid=x.pid, n=wt), strat))
            for t in SAFE + SAFE_DATA:
                stats["amb_safe"] += 1
                stats["amb_false"] += any(i["type"] == "revealed_answer"
                                          for i in prompts.check_response(t.format(pid=x.pid, n=wt), strat))
            continue
        if str(n) in fact_nums:
            continue
        for matcher, tag in ((OLD_NUM, "old"), (prompts.NUM, "new")):
            prompts.NUM = matcher
            for t in LEAKS:
                hit = any(i["type"] == "revealed_answer" for i in prompts.check_response(t.format(pid=x.pid, n=n), strat))
                stats[f"caught_{tag}"] += hit
                if tag == "new":
                    stats["leaks"] += 1
            for t in SAFE:
                hit = any(i["type"] == "revealed_answer" for i in prompts.check_response(t.format(pid=x.pid), strat))
                stats[f"false_{tag}"] += hit
                if tag == "new":
                    stats["safe"] += 1
        prompts.NUM = NEW_NUM
    return stats


NEW_NUM = prompts.NUM


def main() -> None:
    kb = KnowledgeBase()
    kb.load_or_build()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:   # Windows keeps the SQLite file open
        agent = _agent(Path(tmp), kb)
        rng = random.Random(2026)
        algos = ["FCFS", "SJF", "SRTF", "RR", "PRIORITY_NP", "PRIORITY_P"]
        problems = [generator.generate_scheduling(algos[i % 6], 1 + i % 3, seed=rng.randrange(10**8)) for i in range(120)]
        r_ok, r_n, r_miss = check_routing(agent)
        p_ok, p_n, p_miss = check_problem_parsing(problems)
        ans = check_answers(agent, problems)
        g = check_guard(agent, problems)
    pct = lambda a, b: f"{100 * a / b:.0f}% ({a}/{b})"                  # noqa: E731
    rows = [
        ("Messages routed to the expected action (rules + keyword fallback, LLM off)", pct(r_ok, r_n)),
        ("Pasted problems read exactly (120 problems × 6 layouts)", pct(p_ok, p_n)),
        ("Correct typed answers marked correct (120 problems × 4 formats)", pct(ans["right_ok"], ans["right_n"])),
        ("Injected mistake (WT = TAT) found", pct(ans["wrong_ok"], ans["wrong_n"])),
        ("Leaking hints blocked by the guard, before / after the fix",
         f"{100 * g['caught_old'] / g['leaks']:.0f}% / {100 * g['caught_new'] / g['leaks']:.0f}% ({g['leaks']} replies)"),
        ("Safe hints wrongly blocked, before / after the fix",
         f"{100 * g['false_old'] / g['safe']:.0f}% / {100 * g['false_new'] / g['safe']:.0f}% ({g['safe']} replies)"),
        ("Hidden value also in the problem data: leaking hints blocked",
         pct(g["amb_caught"], g["amb_leaks"]) if g["amb_leaks"] else "no such case"),
        ("Hidden value also in the problem data: safe hints wrongly blocked",
         pct(g["amb_false"], g["amb_safe"]) if g["amb_safe"] else "no such case"),
    ]
    table = "| Check | Result |\n|---|---|\n" + "\n".join(f"| {a} | {b} |" for a, b in rows)
    notes = ("\n\nRouting misses:\n" + "\n".join(f"- {m}" for m in r_miss) if r_miss else "") + \
        ("\n\nParsing misses (first few):\n" + "\n".join(f"- {m}" for m in p_miss) if p_miss else "") + \
        ("\n\nAnswer misses (first few):\n" + "\n".join(f"- {m}" for m in ans["misses"]) if ans["misses"] else "") + \
        (f"\n\nGuard cases where the hidden value also appears in the problem data: {g['excluded']}. They are judged by "
         "context (the number next to the hidden quantity, e.g. \"P2's waiting time is 4\"); a leak that names no quantity, "
         "like \"It should come out to 4.\", cannot be told apart from the data.")
    print(table + notes)
    (OUT / "results_chat_checks.md").write_text(table + notes + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
