"""
Counting-semaphore tracer for the OS Engine. Two definitions are in use in the course:

style="blocking" (OSTEP, Silberschatz 6.6, the Theory "Semaphore" slides):
    wait(S):   S.value--; if S.value < 0: add caller to S's queue and block it
    signal(S): S.value++; if S.value <= 0: remove one process from the queue (FIFO) and wake it
    So a negative value -k means k processes are waiting on S.

style="busy_wait" (Module 4 class notes: P(S){ while (S <= 0); S--; }  V(S){ S++; }):
    wait(S):   if S > 0: S--; otherwise the caller keeps spinning and S stays 0
    signal(S): S++; if processes are spinning on S, the first one (FIFO, an assumption) now passes: S--
    So S never goes below 0.

The two give the same waiting processes at every step; only the value differs (busy_wait = max(0, blocking)).
"""
from __future__ import annotations


def trace(initial: dict[str, int], ops: list[dict], style: str = "blocking") -> dict:
    """
    initial: {"S": 1, "mutex": 1, ...}
    ops:     [{"pid": "P1", "op": "wait", "sem": "S"}, ...]  executed in the given order
    style:   "blocking" (value can go negative) or "busy_wait" (value never below 0)
    """
    if style == "busy_wait":
        res = trace(initial, ops, "blocking")
        shown = lambda v: max(0, v)  # noqa: E731
        for st in res["steps"]:
            st["value_before"], st["value_after"] = shown(st["value_before"]), shown(st["value_after"])
            st["effect"] = (st["effect"].replace("blocks (S<0)", "spins in while (S <= 0); S stays 0")
                            .replace("is woken up", "stops spinning and takes it (S back to 0)"))
        res["final_values"] = {k: shown(v) for k, v in res["final_values"].items()}
        res["style"] = "busy_wait"
        return res
    value = dict(initial)
    queues: dict[str, list[str]] = {s: [] for s in value}
    blocked: set[str] = set()
    steps: list[dict] = []
    for n, o in enumerate(ops, start=1):
        pid, op, sem = o["pid"].strip().upper(), o["op"].strip().lower(), o["sem"].strip()
        if sem not in value:
            raise ValueError(f"Step {n}: unknown semaphore {sem}.")
        if op not in ("wait", "signal"):
            raise ValueError(f"Step {n}: operation must be wait or signal.")
        before = value[sem]
        if pid in blocked:
            steps.append({"step": n, "pid": pid, "op": op, "sem": sem, "value_before": before,
                          "value_after": before, "effect": "invalid: process is blocked and cannot run",
                          "woken": None, "queues": {k: list(v) for k, v in queues.items()}})
            continue
        woken = None
        if op == "wait":
            value[sem] -= 1
            if value[sem] < 0:
                queues[sem].append(pid)
                blocked.add(pid)
                effect = f"{pid} blocks (S<0)"
            else:
                effect = f"{pid} proceeds"
        else:
            value[sem] += 1
            if value[sem] <= 0 and queues[sem]:
                woken = queues[sem].pop(0)
                blocked.discard(woken)
                effect = f"{pid} signals; {woken} is woken up"
            else:
                effect = f"{pid} signals; nobody was waiting"
        steps.append({"step": n, "pid": pid, "op": op, "sem": sem, "value_before": before,
                      "value_after": value[sem], "effect": effect, "woken": woken,
                      "queues": {k: list(v) for k, v in queues.items()}})
    return {"steps": steps, "final_values": value, "blocked": sorted(blocked),
            "queues": {k: list(v) for k, v in queues.items()}, "style": "blocking"}


def format_op(o: dict) -> str:
    return f"{o['pid']}: {o['op']}({o['sem']})"
