"""
Deadlock detection for the OS Engine (Module 3 notes, slides 206–208 and 258–262).

* detect(): the detection algorithm for several instances per resource type. It is the safety algorithm with
  Request in place of Need, and Finish[i] starts true for a process that holds nothing (it cannot be part of a
  deadlock). Processes still unfinished at the end are deadlocked.
* Resource-allocation graphs: build one from edges, list its cycles, derive the wait-for graph. A cycle means
  deadlock only when every resource on it has a single instance; otherwise the detection algorithm decides.

Checked against the two worked examples in rag/sources/notes_module3_deadlocks.md (see tests/test_deadlock.py).
"""
from __future__ import annotations

from engine.bankers import _add, _le

Vector = list[int]
Matrix = list[list[int]]


def detect(available: Vector, allocation: Matrix, request: Matrix, scan: str = "cyclic",
           names: list[str] | None = None) -> dict:
    """Detection algorithm. Returns the order processes can finish in, the step trace and the deadlocked set."""
    n, m = len(allocation), len(available)
    names = names or [f"P{k}" for k in range(n)]
    if len(request) != n:
        raise ValueError("Allocation and Request must have the same number of processes.")
    for i, (al, rq) in enumerate(zip(allocation, request)):
        if len(al) != m or len(rq) != m:
            raise ValueError(f"P{i}: every row needs {m} resource values.")
        if any(v < 0 for v in al + rq):
            raise ValueError(f"P{i}: values cannot be negative.")
    if any(v < 0 for v in available):
        raise ValueError("Available cannot be negative.")
    work = list(available)
    finish = [not any(al) for al in allocation]           # holding nothing: cannot be deadlocked
    sequence, steps = [], []
    i, progress = 0, True
    while progress and not all(finish):
        progress = False
        order = list(range(i, n)) + list(range(0, i)) if scan == "cyclic" else list(range(n))
        for j in order:
            if finish[j] or not _le(request[j], work):
                continue
            before = list(work)
            work = _add(work, allocation[j])
            finish[j] = True
            sequence.append(names[j])
            steps.append({"step": len(sequence), "process": names[j], "request": request[j], "work_before": before,
                          "allocation_released": allocation[j], "work_after": list(work)})
            progress, i = True, (j + 1) % n
            break
    deadlocked = [names[k] for k in range(n) if not finish[k]]
    return {"deadlock": bool(deadlocked), "deadlocked": deadlocked, "sequence": sequence, "steps": steps,
            "skipped": [names[k] for k in range(n) if not any(allocation[k])], "final_work": work}


def verify_order(available: Vector, allocation: Matrix, request: Matrix, order: list[str]) -> bool:
    """Is this an order in which every process can finish (any valid order is accepted, like Banker's)?"""
    work, done = list(available), set()
    for p in order:
        k = int(p.strip().upper().lstrip("P"))
        if k in done or not _le(request[k], work):
            return False
        work, done = _add(work, allocation[k]), done | {k}
    return all(k in done or not any(allocation[k]) for k in range(len(allocation)))


# ============================================================================ resource-allocation graphs
def graph_to_matrices(processes: list[str], resources: dict[str, int], holds: list[tuple], wants: list[tuple]) -> dict:
    """holds: (process, resource, count) assignment edges R → P; wants: (process, resource, count) request edges P → R."""
    rnames = list(resources)
    pidx = {p: i for i, p in enumerate(processes)}
    alloc = [[0] * len(rnames) for _ in processes]
    req = [[0] * len(rnames) for _ in processes]
    for table, edges, what in ((alloc, holds, "holds"), (req, wants, "requests")):
        for p, r, c in edges:
            if p not in pidx or r not in resources:
                raise ValueError(f"Unknown process or resource in '{p} {what} {r}'.")
            if int(c) < 1:
                raise ValueError(f"'{p} {what} {r}': the count must be at least 1.")
            table[pidx[p]][rnames.index(r)] += int(c)
    held = [sum(row[j] for row in alloc) for j in range(len(rnames))]
    for j, r in enumerate(rnames):
        if held[j] > resources[r]:
            raise ValueError(f"{r} has {resources[r]} instance(s) but {held[j]} are held.")
    return {"allocation": alloc, "request": req, "available": [resources[r] - held[j] for j, r in enumerate(rnames)],
            "resources": rnames}


def find_cycles(edges: list[tuple[str, str]], limit: int = 12) -> list[list[str]]:
    """Simple cycles of a small directed graph, each listed once, starting from its smallest node."""
    adj: dict[str, list[str]] = {}
    for a, b in edges:
        adj.setdefault(a, [])
        if b not in adj[a]:
            adj[a].append(b)
    nodes = sorted({x for e in edges for x in e}, key=lambda s: (len(s), s))
    rank = {v: k for k, v in enumerate(nodes)}
    cycles: list[list[str]] = []

    def dfs(start: str, v: str, path: list[str]):
        for w in adj.get(v, []):
            if len(cycles) >= limit:
                return
            if w == start:
                cycles.append(path[:])
            elif w not in path and rank[w] > rank[start]:
                dfs(start, w, path + [w])

    for s in nodes:
        dfs(s, s, [s])
    return cycles


def analyse_graph(processes: list[str], resources: dict[str, int], holds: list[tuple], wants: list[tuple]) -> dict:
    """Everything the tutor says about a resource-allocation graph: cycles, wait-for graph, detection verdict."""
    mats = graph_to_matrices(processes, resources, holds, wants)
    rag_edges = [(r, p) for p, r, _ in holds] + [(p, r) for p, r, _ in wants]
    cycles = find_cycles(rag_edges)
    holders = {r: {p for p, rr, _ in holds if rr == r} for r in resources}
    wfg = sorted({(p, q) for p, r, _ in wants for q in holders[r] if q != p})
    single = all(n == 1 for n in resources.values())
    det = detect(mats["available"], mats["allocation"], mats["request"], names=processes)
    if not cycles:
        why = "The graph has no cycle, so there is no deadlock."
    elif single:
        why = "Every resource has one instance and the graph has a cycle, so the processes on it are deadlocked."
    elif det["deadlock"]:
        why = ("The graph has a cycle and, running the detection algorithm, "
               f"{', '.join(det['deadlocked'])} can never get what they request: deadlock.")
    else:
        why = ("The graph has a cycle, but some resources have several instances, so a cycle alone does not mean "
               "deadlock. The detection algorithm finds an order in which every process finishes: no deadlock.")
    return {**mats, "cycles": cycles, "wait_for": wfg, "wait_for_cycles": find_cycles(wfg), "single_instance": single,
            "detection": det, "deadlock": det["deadlock"], "why": why}
