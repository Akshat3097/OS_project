"""
Past-paper question bank: questions from previous-year papers, solved and checked by the OS Engine.

Files: data/question_bank/*.json (see TEMPLATE.json.example and vit_bcse303_papers.json).
Kinds of entries
  "scheduling"  single CPU burst per process          -> engine.scheduling (full error analysis in Practice)
  "advanced"    CPU/I-O bursts, multilevel queues,     -> engine.advanced
                fractional times
  "bankers"     Banker's safety (+ optional request);  -> engine.bankers
                "mode": "detection" = deadlock detection (Need = outstanding Request)

    python -m engine.question_bank        # compare every entry with its official answer key
"""
from __future__ import annotations

import json
import random

import config
from engine import bankers, scheduling
from engine.advanced import AdvancedProblem, Job, QueueSpec, performance
from engine.generator import BankersProblem, SchedulingProblem
from engine.scheduling import Process

BANK_DIR = config.DATA_DIR / "question_bank"


def load() -> list[dict]:
    items = []
    if not BANK_DIR.exists():
        return items
    for f in sorted(BANK_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"Skipping {f.name}: {e}")
            continue
        for it in (data if isinstance(data, list) else [data]):
            it.setdefault("source", it.get("paper", f.stem))
            it.setdefault("kind", "advanced" if "jobs" in it else "scheduling")
            items.append(it)
    return items


def to_problem(item: dict):
    kind = item.get("kind", "scheduling")
    if kind == "bankers":
        return BankersProblem(2, item["available"], item["maximum"], item["allocation"],
                              item.get("resources", ["A", "B", "C", "D"][:len(item["available"])]))
    if kind == "advanced":
        jobs = [Job(j["pid"], j["arrival"], [tuple(b) for b in j["bursts"]], j.get("priority", 0), j.get("queue", 1))
                for j in item["jobs"]]
        queues = [QueueSpec(q["qid"], q["algorithm"], q.get("quantum")) for q in item["queues"]] if item.get("queues") else None
        return AdvancedProblem(jobs, item.get("algorithm"), item.get("quantum"), queues,
                               item.get("lower_is_higher", True), 3, f"[{item.get('paper', '')} {item.get('question', '')}]",
                               feedback=item.get("feedback", False), queue_preempt=item.get("queue_preempt", "immediate"))
    procs = [Process(p["pid"], int(p["arrival"]), int(p["burst"]), int(p.get("priority", 0))) for p in item["processes"]]
    return SchedulingProblem(item["algorithm"].upper(), 2, procs, item.get("quantum"), seed=None)


def is_notes_example(item: dict) -> bool:
    """Worked examples from the class notes (ids NOTES-… / THEORY-…), as opposed to past CAT/FAT papers."""
    return str(item.get("id", "")).upper().startswith(("NOTES-", "THEORY-"))


def random_problem(kind: str | None = None, source: str | None = None):
    """source: None (any), "papers" (past papers) or "notes" (worked examples from the class notes)."""
    items = [i for i in load() if (kind is None or i.get("kind") == kind)
             and (source is None or is_notes_example(i) == (source == "notes"))]
    if not items:
        return None
    it = random.choice(items)
    return to_problem(it), it


def _close(a, b, tol=0.011) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def check(item: dict) -> dict:
    """Compare the engine's answer with the official key. match: True / False / None (nothing to compare)."""
    off = item.get("official") or {}
    prob = to_problem(item)
    row = {"id": item.get("id"), "paper": item.get("paper", item.get("source")), "question": item.get("question"),
           "kind": item.get("kind"), "checks": [], "notes": item.get("notes", "")}
    if item.get("kind") == "bankers":
        av, mx, al = item["available"], item["maximum"], item["allocation"]
        res = bankers.safety(av, mx, al)
        row["engine"] = f"{'safe' if res['safe'] else 'unsafe'} {', '.join(res['sequence'] or res['partial_sequence'])}"
        if "safe" in off:
            row["checks"].append(("safe/unsafe", res["safe"] == off["safe"]))
        if off.get("sequence"):
            row["checks"].append(("official sequence is valid",
                                  bankers.verify_sequence(av, mx, al, off["sequence"])["valid"]))
        for alt in off.get("also_accepted", []):
            row["checks"].append(("alternative sequence is valid", bankers.verify_sequence(av, mx, al, alt)["valid"]))
        if off.get("sequence_after_fix"):
            fixed = [a + b for a, b in zip(av, [0, 1, 0])] if item.get("mode") == "detection" else av
            row["checks"].append(("safe after adding one Q", bankers.verify_sequence(fixed, mx, al, off["sequence_after_fix"])["valid"]))
        if item.get("request") and "request_granted" in off:
            pid, vec = item["request"]["process"], item["request"]["vector"]
            rq = bankers.request(av, mx, al, pid, vec)
            row["engine"] += f" · request: {'granted' if rq['granted'] else 'refused (' + rq['reason'] + ')'}"
            row["checks"].append(("request decision", rq["granted"] == off["request_granted"]))
            if off.get("sequence_after_request"):
                av2 = [a - r for a, r in zip(av, vec)]
                al2 = [[a + (r if i == pid else 0) for a, r in zip(row_, vec)] for i, row_ in enumerate(al)]
                row["checks"].append(("sequence after the request is valid",
                                      bankers.verify_sequence(av2, mx, al2, off["sequence_after_request"])["valid"]))
    else:
        if item.get("kind") == "advanced":
            res = prob.solve()
            ct = {k: v.completion for k, v in res.results.items()}
            wt_ex, wt_in = res.avg("waiting"), res.avg("waiting_incl_io")
            tat = res.avg("turnaround")
            rt = res.avg("response")
            wt_by = {k: (v.waiting, v.waiting_incl_io) for k, v in res.results.items()}
        else:
            res = prob.solve()
            ct = {k: v.completion for k, v in res.results.items()}
            wt_ex = wt_in = res.avg_wt
            tat, rt = res.avg_tat, res.avg_rt
            wt_by = {k: (v.waiting, v.waiting) for k, v in res.results.items()}
        row["engine"] = f"avg WT {wt_ex:.2f}" + (f" (I/O as waiting: {wt_in:.2f})" if abs(wt_in - wt_ex) > 1e-9 else "") + \
                        f", avg TAT {tat:.2f}"
        if off.get("ct"):
            row["checks"].append(("completion times", all(_close(ct[k], v) for k, v in off["ct"].items())))
        if off.get("wt"):
            row["checks"].append(("waiting times", all(_close(wt_by[k][0], v) for k, v in off["wt"].items())
                                  or all(_close(wt_by[k][1], v) for k, v in off["wt"].items())))
        if "avg_tat" in off:
            row["checks"].append(("average TAT", _close(tat, off["avg_tat"])))
        if "avg_wt" in off:
            row["checks"].append(("average WT", _close(wt_ex, off["avg_wt"]) or _close(wt_in, off["avg_wt"])))
        if "avg_rt" in off:
            row["checks"].append(("average RT", _close(rt, off["avg_rt"])))
        if any(k in off for k in ("cpu_utilization", "throughput", "context_switches")):
            perf = performance(res.gantt, len(res.results))
            row["engine"] += f", CPU {perf['cpu_utilization']}%, {perf['context_switches']} context switches"
            if "cpu_utilization" in off:
                row["checks"].append(("CPU utilisation", _close(perf["cpu_utilization"], off["cpu_utilization"], 0.06)))
            if "throughput" in off:
                row["checks"].append(("throughput", _close(perf["throughput"], off["throughput"], 0.006)))
            if "context_switches" in off:
                row["checks"].append(("context switches", perf["context_switches"] == off["context_switches"]))
    row["match"] = all(ok for _, ok in row["checks"]) if row["checks"] else None
    return row


def check_all() -> list[dict]:
    return [check(it) for it in load()]


if __name__ == "__main__":
    rows = check_all()
    if not rows:
        print(f"No questions found in {BANK_DIR}.")
    for r in rows:
        status = "no official answer" if r["match"] is None else ("OK " if r["match"] else "MISMATCH")
        failed = [n for n, ok in r["checks"] if not ok]
        print(f"{status:9} {r['id']:<28} {r['engine']}" + (f"  ✗ {', '.join(failed)}" if failed else ""))
        if r["notes"] and not r["match"]:
            print(f"          note: {r['notes']}")
