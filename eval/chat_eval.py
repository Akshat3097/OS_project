"""
Compare the plain model, the prompt-customized tutor and the fine-tuned tutor on held-out tasks,
scored automatically against the OS Engine (no human judging needed).

    python -m eval.chat_eval                                  # every installed one of the three models
    python -m eval.chat_eval --models llama3.1:8b os-tutor --n 6

Tasks (fresh problems, generated with seeds the training data did not use):
  numerical   solve a scheduling problem; the reported average waiting time is checked against the engine
  bankers     is the state safe or unsafe? checked against the engine
  facts       10 yes/no questions on the course conventions; the first word of the reply is checked
  hinting     the student shows an answer with one mistake; good = asks a guiding question, names the right
              process, and does not give the corrected value away
Also reported: reply length, share of replies ending in a question, speed.
Writes eval/results_chat.md (a table to paste into the report) and eval/results_chat.json.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from pathlib import Path

import config
from engine import bankers, generator
from tutor.llm import OllamaClient

URL = "http://127.0.0.1:11434"
OUT = Path(__file__).resolve().parent
ALGOS = ["FCFS", "SJF", "SRTF", "RR", "PRIORITY_NP"]
SAY = {"FCFS": "FCFS", "SJF": "non-preemptive SJF", "SRTF": "SRTF (preemptive SJF)", "RR": "Round Robin",
       "PRIORITY_NP": "non-preemptive priority (lower number = higher priority)"}

FACTS = [
    ("In SRTF, a new process arrives with exactly the same remaining time as the running process. Does it preempt "
     "the running process? Answer yes or no first, then explain briefly.", "no"),
    ("In Round Robin, does a process that arrives exactly when the running process's quantum ends join the ready "
     "queue before the preempted process (the usual course convention)? Answer yes or no first.", "yes"),
    ("Does an unsafe state in the Banker's algorithm mean the system is already deadlocked? Answer yes or no first.", "no"),
    ("If resources have several instances, does a cycle in the resource-allocation graph always mean deadlock? "
     "Answer yes or no first.", "no"),
    ("In the blocking implementation of semaphores, can a semaphore's value become negative? Answer yes or no first.", "yes"),
    ("Does test-and-set on its own guarantee bounded waiting? Answer yes or no first.", "no"),
    ("Is turnaround time equal to completion time minus arrival time? Answer yes or no first.", "yes"),
    ("Is the safe sequence in the Banker's algorithm always unique? Answer yes or no first.", "no"),
    ("In non-preemptive SJF, can a newly arrived shorter job interrupt the running process? Answer yes or no first.", "no"),
    ("Is waiting time equal to turnaround time minus burst time for a process with no I/O? Answer yes or no first.", "yes"),
]


def chat(model: str, prompt: str) -> tuple[str, float, int]:
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False,
                       # the app's settings (output cap, repetition penalty), temperature 0 to repeat runs
                       "options": {**config.LLM_OPTIONS, "temperature": 0}}).encode()
    req = urllib.request.Request(f"{URL}/api/chat", data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.load(r)
    return d["message"]["content"], time.time() - t0, d.get("eval_count", 0)


def problem_prompt(p) -> str:
    rows = ", ".join(f"{q.pid} AT={q.arrival} BT={q.burst}" + (f" priority={q.priority}" if p.algorithm.startswith("PRIORITY") else "")
                     for q in p.processes)
    quantum = f" with time quantum {p.quantum}" if p.quantum else ""
    return (f"Solve using {SAY[p.algorithm]}{quantum}: {rows}. Draw the Gantt chart and give the average waiting time.")


def reported_avg_wt(text: str) -> float | None:
    for line in reversed(text.splitlines()):
        low = line.lower()
        if "average" in low and ("wait" in low or "wt" in low):
            tail = line.split("=")[-1] if "=" in line else line
            nums = re.findall(r"-?\d+(?:\.\d+)?", tail)
            if nums:
                return float(nums[-1] if "=" in line else nums[0])
    return None


def first_word(text: str) -> str:
    m = re.search(r"[A-Za-z]+", text)
    return m.group(0).lower() if m else ""


def tasks(n: int) -> list[dict]:
    out = []
    for i in range(n):
        algo = ALGOS[i % len(ALGOS)]
        p = generator.generate_scheduling(algo, 1 + i % 2, seed=880_000 + i)
        out.append({"kind": "numerical", "prompt": problem_prompt(p), "answer": p.solve().avg_wt})
    want, seed, picked = max(2, n // 2), 990_000, []
    while len(picked) < want:                                # half safe, half unsafe states
        b = generator.generate_bankers(2 + seed % 2, seed=seed)
        seed += 1
        safe = bankers.safety(b.available, b.maximum, b.allocation)["safe"]
        if sum(1 for _, s_ in picked if s_ == safe) < (want + 1) // 2:
            picked.append((b, safe))
    for b, safe in picked:
        alloc = ", ".join(f"P{k} " + " ".join(map(str, r)) for k, r in enumerate(b.allocation))
        mx = ", ".join(f"P{k} " + " ".join(map(str, r)) for k, r in enumerate(b.maximum))
        prompt = (f"Banker's algorithm, resources {' '.join(b.resources)}. Allocation: {alloc}. Max: {mx}. "
                  f"Available: {' '.join(map(str, b.available))}. Is the system in a safe state?")
        out.append({"kind": "bankers", "prompt": prompt, "answer": safe})
    for q, a in FACTS:
        out.append({"kind": "facts", "prompt": q, "answer": a})
    for i in range(max(3, n // 2)):
        algo = ALGOS[i % len(ALGOS)]
        p = generator.generate_scheduling(algo, 2, seed=770_000 + i)
        res = p.solve()
        rs = list(res.results.values())
        wrong = rs[len(rs) // 2]
        cells = []
        for r in rs:
            wt = r.turnaround if r.pid == wrong.pid else r.waiting       # one mistake: WT = TAT for one process
            cells.append(f"{r.pid}: CT {r.completion}, TAT {r.turnaround}, WT {wt}")
        prompt = (f"I solved this with {SAY[algo]}" + (f" (q = {p.quantum})" if p.quantum else "") + ": "
                  + ", ".join(f"{q.pid} AT={q.arrival} BT={q.burst}" + (f" priority={q.priority}" if algo.startswith("PRIORITY") else "")
                              for q in p.processes)
                  + ". My answer: " + "; ".join(cells) + ". Is it right?")
        out.append({"kind": "hinting", "prompt": prompt, "pid": wrong.pid, "secret": wrong.waiting,
                    "given": wrong.turnaround})
    return out


def score(t: dict, reply: str) -> bool:
    if t["kind"] == "numerical":
        x = reported_avg_wt(reply)
        return x is not None and abs(x - t["answer"]) <= 0.05
    if t["kind"] == "bankers":
        low = reply.lower()
        unsafe = bool(re.search(r"\bunsafe\b|not (in )?a? ?safe|is not safe|no safe sequence", low))
        safe = not unsafe and bool(re.search(r"\bsafe\b", low))
        return unsafe if not t["answer"] else safe
    if t["kind"] == "facts":
        return first_word(reply) == t["answer"]
    nums = set(re.findall(r"(?<![\d.])\d+(?![\d.])", reply))
    revealed = str(t["secret"]) in nums and t["secret"] != t["given"]
    return "?" in reply and t["pid"] in reply and not revealed


def main() -> None:
    global URL
    import os
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", default=None)
    ap.add_argument("--n", type=int, default=10, help="numerical problems per model (other tasks scale with it)")
    args = ap.parse_args()
    URL = os.environ.get("TUTOR_OLLAMA_URL", URL).rstrip("/")
    with urllib.request.urlopen(f"{URL}/api/tags", timeout=5) as r:
        installed = [m["name"] for m in json.load(r)["models"]]
    have = lambda m: any(i == m or i.split(":")[0] == m for i in installed)  # noqa: E731
    models = args.models or [m for m in ("llama3.1:8b", "os-tutor-prompt", "os-tutor", "os-tutor-v2") if have(m)]
    ts = tasks(args.n)
    print(f"{len(ts)} tasks × {len(models)} models")
    results = {}
    for m in models:
        OllamaClient(url=URL, model=m).make_room()     # only one 8B model fits on the 8 GB laptop
        rows = []
        for k, t in enumerate(ts, 1):
            reply, secs, toks = chat(m, t["prompt"])
            ok = score(t, reply)
            rows.append({"kind": t["kind"], "ok": ok, "secs": secs, "tokens": toks, "words": len(reply.split()),
                         "ends_with_question": reply.strip().endswith("?"), "reply": reply})
            print(f"  {m:<16} {k:>2}/{len(ts)} {t['kind']:<9} {'✓' if ok else '✗'}  {secs:4.1f}s")
        results[m] = rows

    def pct(rows, kind=None):
        sel = [r for r in rows if kind is None or r["kind"] == kind]
        return f"{100 * sum(r['ok'] for r in sel) / len(sel):.0f}% ({sum(r['ok'] for r in sel)}/{len(sel)})" if sel else "—"

    head = "| Metric | " + " | ".join(models) + " |\n|---|" + "---|" * len(models)
    lines = [head,
             "| Numerical: correct average WT | " + " | ".join(pct(results[m], "numerical") for m in models) + " |",
             "| Banker's: safe/unsafe correct | " + " | ".join(pct(results[m], "bankers") for m in models) + " |",
             "| Course facts (yes/no) correct | " + " | ".join(pct(results[m], "facts") for m in models) + " |",
             "| Hint-first on a wrong answer | " + " | ".join(pct(results[m], "hinting") for m in models) + " |",
             "| Replies ending in a question | " + " | ".join(
                 f"{100 * sum(r['ends_with_question'] for r in results[m]) / len(results[m]):.0f}%" for m in models) + " |",
             "| Average reply length (words) | " + " | ".join(
                 f"{sum(r['words'] for r in results[m]) / len(results[m]):.0f}" for m in models) + " |",
             "| Average time per reply (s) | " + " | ".join(
                 f"{sum(r['secs'] for r in results[m]) / len(results[m]):.1f}" for m in models) + " |"]
    table = "\n".join(lines)
    print("\n" + table)
    (OUT / "results_chat.md").write_text(table + "\n", encoding="utf-8")
    (OUT / "results_chat.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\nSaved eval/results_chat.md and eval/results_chat.json")


if __name__ == "__main__":
    main()
